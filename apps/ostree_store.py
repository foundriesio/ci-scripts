import subprocess
import os
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

    def _cmd(self, cmd):
        cmd_args = cmd.split()
        full_cmd = ['ostree', '--repo={}'.format(self._repo_dir)]
        full_cmd.extend(cmd_args)
        return subprocess.check_output(full_cmd, stderr=subprocess.STDOUT, universal_newlines=True).rstrip()


class OSTreeTargetAppsStore(TargetAppsStore):
    def __init__(self, repo_dir, create=False, factory=None, creds_arch=None):
        self._repo = OSTreeRepo(repo_dir, create=create, raise_exception=False)
        self._factory = factory
        self._creds_arch = creds_arch

    def branch(self, target: FactoryClient.Target):
        tag = '_'.join(target.tags)
        return 'org.foundries.io/{}/{}/{}'.format(self._factory, tag, target.platform)

    def initialized(self):
        return self._repo.initialized()

    def store(self, target: FactoryClient.Target, images_dir: str, push_to_treehub: bool = True):
        if not self._repo.initialized():
            self._repo.create()
        self._remove_and_index_character_devices(images_dir)
        branch = self.branch(target)
        hash = self._repo.commit(images_dir, branch)
        if push_to_treehub:
            self._push_to_treehub(branch)

        return branch, hash

    def copy(self, target: FactoryClient.Target, dst_repo: OSTreeRepo):
        dst_repo.pull_local(self._repo.dir, self.branch(target))

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
    def _remove_and_index_character_devices(tree_to_commit):
        # TODO: We cannot just simply remove non-regular files (character devices),
        # since overlayfs uses them for removing files from a lower layer
        char_dev_list = subprocess.check_output(['find', tree_to_commit, '-type', 'c'])
        for dev_file in char_dev_list.splitlines():
            logger.info('Removing non-regular file: ' + dev_file.decode('utf-8'))
            os.remove(dev_file)

    def _push_to_treehub(self, ref):
        exit_code = 1
        push_process = None
        logger.info('Pushing Compose Apps to Treehub, ref: {} ...'.format(ref))
        try:
            push_process = subprocess.Popen(['garage-push', '--repo', self._repo.dir,
                                             '--credentials', self._creds_arch, '--ref', ref,
                                             '-v'], universal_newlines=True)
            push_process_output, _ = push_process.communicate(timeout=600)
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
