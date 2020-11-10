import subprocess
import os

from apps.target_apps_store import TargetAppsStore
from factory_client import FactoryClient


class OSTreeRepo:
    @property
    def dir(self):
        return self._repo_dir

    def __init__(self, repo_dir, mode='archive'):
        self._repo_dir = repo_dir
        self._mode = mode

        if not self.initialized():
            self._create()

    def initialized(self):
        return os.path.exists(os.path.join(self._repo_dir, 'config'))

    def commit(self, dir_to_commit, branch):
        commit_hash = self._cmd('commit --tree=dir={} --branch {} --generate-sizes'
                                .format(dir_to_commit, branch))
        return commit_hash

    def refs(self):
        return self._cmd('refs')

    def rev_parse(self, branch):
        return self._cmd('rev-parse {}'.format(branch))

    def cat(self, commit_hash, path):
        return self._cmd('cat {} {}'.format(commit_hash, path))

    def _create(self):
        self._cmd('init --mode {}'.format(self._mode))

    def _cmd(self, cmd):
        cmd_args = cmd.split()
        full_cmd = ['ostree', '--repo={}'.format(self._repo_dir)]
        full_cmd.extend(cmd_args)
        return subprocess.check_output(full_cmd).decode('utf-8').rstrip()


class OSTreeTargetAppsStore(TargetAppsStore):
    def __init__(self, factory, repo_dir, cred_arch):
        self._factory = factory
        self._repo = OSTreeRepo(repo_dir)
        self._cred_arch = cred_arch

    def branch(self, tag, platform):
        return 'org.foundries.io/{}/{}/{}'.format(self._factory, tag, platform)

    def store(self, target: FactoryClient.Target, images_dir: str):
        self._remove_and_index_character_devices(images_dir)
        tag = '_'.join(target.tags)
        branch = self.branch(tag, target.platform)
        hash = self._repo.commit(images_dir, branch)
        self._push_to_treehub(hash)

        return hash

    def _remove_and_index_character_devices(self, tree_to_commit):
        char_dev_list = subprocess.check_output(['find', tree_to_commit, '-type', 'c'])
        print(char_dev_list)
        for dev_file in char_dev_list.splitlines():
            os.remove(dev_file)

    def _push_to_treehub(self, hash):
        push = subprocess.Popen(['garage-push', '--repo', self._repo.dir,
                                 '--credentials', self._cred_arch, '--ref', hash])

        push.wait()
        push.terminate()
