import subprocess
import os
import stat
import logging
import shutil
from tempfile import TemporaryDirectory
from uuid import uuid4

from apps.target_apps_store import TargetAppsStore
from factory_client import FactoryClient


logger = logging.getLogger(__name__)


class OSTreeRepo:
    @property
    def dir(self):
        return self._repo_dir

    def __init__(self, repo_dir, mode='archive', create=False, raise_exception=True):
        self._repo_dir = repo_dir
        self._mode = mode

        if not self.initialized():
            if create:
                self.create()
            else:
                if raise_exception:
                    raise Exception('Failed to create OSTree repo object because an ostree repo'
                                    ' does not exist in the specified directory: {}'.format(repo_dir))

    def initialized(self):
        return os.path.exists(os.path.join(self._repo_dir, 'config'))

    def create(self):
        self._cmd('init --mode {}'.format(self._mode))

    def commit(self, dir_to_commit, branch):
        logger.info('Committing directory `{}` to `{}` branch...'.format(dir_to_commit, branch))
        commit_hash = self._cmd('commit --tree=dir={} --branch {} --generate-sizes'
                                ' --link-checkout-speedup --skip-if-unchanged'
                                .format(dir_to_commit, branch))
        return commit_hash

    def checkout(self, ref, src_dir, dst_dir, require_hardlinks=False):
        if require_hardlinks:
            return self._cmd('checkout --require-hardlinks --union --subpath={} {} {}'.format(src_dir, ref, dst_dir))
        else:
            return self._cmd('checkout --user-mode --union --subpath={} {} {}'.format(src_dir, ref, dst_dir))

    def refs(self):
        return self._cmd('refs')

    def rev_parse(self, branch):
        return self._cmd('rev-parse {}'.format(branch))

    def pull_local(self, src_repo, ref):
        return self._cmd('pull-local {} {}'.format(src_repo, ref))

    def cat(self, commit_hash, path):
        return self._cmd('cat {} {}'.format(commit_hash, path))

    def show(self, ref, with_sizes=False):
        try:
            if not with_sizes:
                cmd = 'show {}'.format(ref)
            else:
                cmd = 'show --print-sizes {}'.format(ref)

            ref_details = self._cmd(cmd)
        except subprocess.CalledProcessError as err:
            ref_details = None
        return ref_details

    def size_in_kbs(self):
        return int(subprocess.check_output(['du', '-sk', self._repo_dir], universal_newlines=True).split()[0])

    def path_exists(self, ref, path):
        ret_value = False
        try:
            self._cmd('ls {} {}'.format(ref, path))
            ret_value = True
        except subprocess.CalledProcessError as err:
            pass

        return ret_value

    def _cmd(self, cmd):
        cmd_args = cmd.split()
        full_cmd = ['ostree', '--repo={}'.format(self._repo_dir)]
        full_cmd.extend(cmd_args)
        return subprocess.check_output(full_cmd, stderr=subprocess.STDOUT, universal_newlines=True).rstrip()


class OSTreeTargetAppsStore(TargetAppsStore):
    WhiteoutsFile = '.whiteouts'
    ContainerImagesDir = 'images'
    AppsDir = 'apps'

    @property
    def dir(self):
        return self._repo.dir

    def __init__(self, repo_dir, create=False, factory=None, creds_arch=None, mode='archive'):
        self._repo = OSTreeRepo(repo_dir, create=create, raise_exception=False, mode=mode)
        self._factory = factory
        self._creds_arch = creds_arch

    def branch(self, target: FactoryClient.Target):
        tag = '_'.join(target.tags)
        return 'org.foundries.io/{}/{}/{}'.format(self._factory, tag, target.platform)

    def initialized(self):
        return self._repo.initialized()

    def store(self, target: FactoryClient.Target, target_dir: str):
        if not self._repo.initialized():
            self._repo.create()
        self._remove_and_record_non_regular_files(os.path.join(target_dir, self.ContainerImagesDir),
                                                  os.path.join(target_dir, self.WhiteoutsFile))
        branch = self.branch(target)
        hash = self._repo.commit(target_dir, branch)

        return '{}@{}'.format(branch, hash)

    def copy(self, target: FactoryClient.Target, dst_repo: OSTreeRepo):
        return dst_repo.pull_local(self._repo.dir, target.apps_commit_hash)

    def copy_and_checkout(self, target: FactoryClient.Target, dst_repo_dir, dst_apps_dir, dst_images_dir):
        logger.info('Copying Target\'s ostree repo; dst: {}'.format(dst_repo_dir))
        dst_repo = OSTreeRepo(dst_repo_dir, 'bare', create=True)
        # ostree pull-local does not support pulling both ref/branch and commit by specifying a single composite uri
        # like <ref/branch>@<commit>, thus two calls have to be made
        dst_repo.pull_local(self._repo.dir, target.apps_commit_hash)
        dst_repo.pull_local(self._repo.dir, self.branch(target))

        logger.info('Checking out Apps from an ostree repo; src={}, dst={}'.format(dst_repo_dir, dst_apps_dir))
        dst_repo.checkout(target.apps_commit_hash, self.AppsDir, dst_apps_dir, require_hardlinks=True)

        logger.info('Checking out Apps\' container images from an ostree repo; src={}, dst={}'.
                    format(dst_repo_dir, dst_images_dir))
        dst_repo.checkout(target.apps_commit_hash, self.ContainerImagesDir, dst_images_dir, require_hardlinks=True)

        logger.info('Applying non-regular files if any...')
        self._apply_whiteouts(target.apps_commit_hash, dst_images_dir)

    def checkout(self, target: FactoryClient.Target, dst_target_dir):
        logger.info('Checking out Target from an ostree repo; src={}, dst={}'.format(self._repo.dir, dst_target_dir))
        os.makedirs(dst_target_dir, exist_ok=True)
        # TODO: support of checkout with hardlinks
        #self._repo._cmd('checkout --require-hardlinks --union {} {}'.format(self.branch(target), dst_target_dir))
        self._repo._cmd('checkout --union {} {}'.format(self.branch(target), dst_target_dir))
        self._apply_whiteouts(self.branch(target), dst_target_dir + '/images')

    def exist(self, target: FactoryClient.Target):
        if not self._repo.initialized():
            # ostree repo is not present at all
            return False

        if not target.apps_uri:
            # there is no apps' commit hash in the given Target at all
            return False

        if target.shortlist:
            # A given Target has shortlisted Apps, while OSTreeTargetAppsStore currently supports
            # only non shortlisted Targets
            return False

        target_commit_hash_info = self._repo.show(target.apps_commit_hash)
        if not target_commit_hash_info:
            # Commit specified in Target does not exists in the repo
            return False

        return True

    @staticmethod
    def _remove_and_record_non_regular_files(root_dir, dst_record_file):
        files_to_record = []
        for root, _, files in os.walk(root_dir):
            for file in files:
                filepath = os.path.join(root, file)
                if os.path.exists(filepath):
                    file_stat = os.stat(filepath)
                    # OSTree allows to commit only regular files and symlinks
                    if not stat.S_ISREG(file_stat.st_mode) and not stat.S_ISLNK(file_stat.st_mode):
                        if file_stat.st_size != 0:
                            logger.error('Not regular file and is its size is not zero, what\'s the heck to do with it?')
                            continue

                        item_path = os.path.relpath(filepath, root_dir)
                        logger.info('Recording a non-regular file: {}'.format(item_path))
                        files_to_record.append((item_path, file_stat.st_mode, file_stat.st_rdev))

        with open(dst_record_file, 'w') as f:
            for item in files_to_record:
                f.write('{} {} {}\n'.format(item[0], item[1], item[2]))
                logger.info('Removing a non-regular file: {}'.format(item[0]))
                os.remove(os.path.join(root_dir, item[0]))

    def _apply_whiteouts(self, commit_hash, dst_images_dir):
        if not self._repo.path_exists(commit_hash, self.WhiteoutsFile):
            logger.info('There are no any non-regular files in the given commit/ref {}'.format(commit_hash))
            return

        self._repo.checkout(commit_hash, self.WhiteoutsFile, dst_images_dir)
        with open(os.path.join(dst_images_dir, self.WhiteoutsFile)) as whiteouts_file:
            for line in whiteouts_file.readlines():
                items = line.split()
                if len(items) != 3:
                    logger.error('Invalid the non-regular file record: expected three items got {}'.format(len(items)))
                    return
                filename = os.path.join(dst_images_dir, items[0])
                filemode = int(items[1])
                filedevice = int(items[2])

                if os.path.exists(filename):
                    logger.info('A non-regular file already exists: {}'.format(filename))
                    continue

                try:
                    logger.info('Creating a non-regular file: {} {} {}'.format(filename, filemode, filedevice))
                    os.mknod(filename, mode=filemode, device=filedevice)
                except Exception as exc:
                    pass
                if not os.path.exists(filename):
                    raise Exception('Failed to create a non-regular file: {}, error: {}'.format(filename, exc))


class ArchOSTreeTargetAppsStore(OSTreeTargetAppsStore):
    def __init__(self, factory, archive_dir, repo_dir, create=True):
        super(ArchOSTreeTargetAppsStore, self).__init__(repo_dir, create=create, factory=factory, mode='bare')
        self._archive_path = os.path.join(archive_dir, self._archive_name(factory))
        if not os.path.exists(self._archive_path):
            logger.info('An archived ostree repo doesn\'t exist: {}'.format(self._archive_path))
            self._new_repo = True
        else:
            self._copy_and_extract_repo()
            self._new_repo = False

    @property
    def archive_path(self):
        return self._archive_path

    def store_archive(self):
        with TemporaryDirectory() as tmp_archive_dir:
            tmp_archive_file = os.path.join(tmp_archive_dir, str(uuid4()))
            subprocess.check_call(['tar', '-cf', tmp_archive_file, '-C', self.dir, '.'])
            logger.info('Copy an archived ostree repo; src: {}, dst: {}'.format(tmp_archive_file, self._archive_path))
            shutil.copy(tmp_archive_file, self._archive_path)

    def exist_branch(self, target: FactoryClient.Target):
        if not self._repo.initialized():
            # ostree repo is not present at all
            return False

        if not target.apps_uri:
            # there is no apps' commit hash in the given Target at all
            return False

        target_ref_info = self._repo.show(self.branch(target))
        return target_ref_info is not None

    @staticmethod
    def _archive_name(factory):
        return '{}_apps_ostree_repo.tar'.format(factory)

    def _copy_and_extract_repo(self):
        with TemporaryDirectory() as tmp_archive_dir:
            tmp_archive_file = os.path.join(tmp_archive_dir, str(uuid4()))
            logger.info('Copy an archived ostree repo; src: {}, dst: {}'.format(self._archive_path, tmp_archive_file))
            shutil.copy(self._archive_path, tmp_archive_file)
            subprocess.check_call(['tar', '-xf', tmp_archive_file, '-C', self.dir])


