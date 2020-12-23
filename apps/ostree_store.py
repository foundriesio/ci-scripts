import subprocess
import os
import stat
import logging

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
                                .format(dir_to_commit, branch))
        return commit_hash

    def checkout(self, ref, src_dir, dst_dir, user_mode=True):
        user_mode_flag = '--user-mode' if user_mode else ''
        return self._cmd('checkout {} --union --subpath={} {} {}'.format(user_mode_flag, src_dir, ref, dst_dir))

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

    def __init__(self, repo_dir, create=False, factory=None, creds_arch=None):
        self._repo = OSTreeRepo(repo_dir, create=create, raise_exception=False)
        self._factory = factory
        self._creds_arch = creds_arch

    def branch(self, target: FactoryClient.Target):
        tag = '_'.join(target.tags)
        return 'org.foundries.io/{}/{}/{}'.format(self._factory, tag, target.platform)

    def initialized(self):
        return self._repo.initialized()

    def store(self, target: FactoryClient.Target, target_dir: str, push_to_treehub: bool = True):
        if not self._repo.initialized():
            self._repo.create()
        self._remove_and_record_non_regular_files(os.path.join(target_dir, self.ContainerImagesDir),
                                                  os.path.join(target_dir, self.WhiteoutsFile))
        branch = self.branch(target)
        hash = self._repo.commit(target_dir, branch)
        if push_to_treehub:
            self._push_to_treehub(branch)

        return branch, hash

    def copy(self, target: FactoryClient.Target, dst_repo: OSTreeRepo):
        dst_repo.pull_local(self._repo.dir, self.branch(target))

    def copy_and_checkout(self, target: FactoryClient.Target, dst_repo_dir, dst_apps_dir, dst_images_dir):
        logger.info('Copying Target\'s ostree repo; dst: {}'.format(dst_repo_dir))
        dst_repo = OSTreeRepo(dst_repo_dir, 'bare-user', create=True)
        dst_repo.pull_local(self._repo.dir, self.branch(target))

        logger.info('Checking out Apps from an ostree repo; src={}, dst={}'.format(dst_repo_dir, dst_apps_dir))
        dst_repo.checkout(target.apps_sha, self.AppsDir, dst_apps_dir)

        logger.info('Checking out Apps\' container images from an ostree repo; src={}, dst={}'.
                    format(dst_repo_dir, dst_images_dir))
        dst_repo.checkout(target.apps_sha, self.ContainerImagesDir, dst_images_dir)

        logger.info('Applying non-regular files if any...')
        self._apply_whiteouts(target.apps_sha, dst_images_dir)

    def exist(self, target: FactoryClient.Target):
        if not self._repo.initialized():
            # ostree repo is not present at all
            return False

        if not target.apps_sha:
            # there is no apps' commit hash in the given Target at all
            return False

        if target.shortlist:
            # A given Target has shortlisted Apps, while OSTreeTargetAppsStore currently supports
            # only non shortlisted Targets
            return False

        target_commit_hash_info = self._repo.show(target.apps_sha)
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

    def _push_to_treehub(self, ref):
        exit_code = 1
        push_process = None
        logger.info('Pushing Compose Apps to Treehub, ref: {} ...'.format(ref))
        try:
            push_process = subprocess.Popen(['garage-push', '--repo', self._repo.dir,
                                             '--credentials', self._creds_arch, '--ref', ref,
                                             '-v'], universal_newlines=True)
            push_process_output, _ = push_process.communicate(timeout=2000)
            exit_code = push_process.returncode
            error_msg = push_process_output
        except subprocess.TimeoutExpired as timeout_exc:
            error_msg = str(timeout_exc)
            push_process.kill()
            push_process.communicate(timeout=10)
        except Exception as exc:
            error_msg = str(exc)

        if exit_code != 0:
            raise Exception('Failed to push Apps ostree repo to Treehub; exit code: {}, error: {}'
                            .format(exit_code, error_msg))
