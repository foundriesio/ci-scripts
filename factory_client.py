import os
import logging
import requests
import subprocess

from helpers import Progress, http_get
from typing import NamedTuple


logger = logging.getLogger(__name__)


class FactoryClient:
    class Target:
        OEArchToAppPlatformMap = {'aarch64': 'arm64', 'x86_64': 'amd64', 'arm': 'arm'}

        def __init__(self, target_name, target_json, shortlist=None):
            self.name = target_name
            self.json = target_json
            self.shortlist = shortlist
            self._set_apps_commit_hash()

        @property
        def platform(self):
            return self.OEArchToAppPlatformMap[self['custom']['arch']]

        @property
        def tags(self):
            return self['custom']['tags']

        @property
        def sha(self):
            return self['custom']['containers-sha']

        @property
        def apps_uri(self):
            return self['custom'].get('compose-apps-uri')

        @apps_uri.setter
        def apps_uri(self, apps_commit_uri: str):
            self['custom']['compose-apps-uri'] = apps_commit_uri
            self._set_apps_commit_hash()

        @property
        def apps_commit_hash(self):
            return self._apps_commit_hash

        @property
        def shortlist(self):
            return self['custom'].get('shortlist')

        @shortlist.setter
        def shortlist(self, shortlist: []):
            self['custom']['shortlist'] = shortlist

        @property
        def lmp_version(self):
            return self['custom'].get('lmp_version')

        @lmp_version.setter
        def lmp_version(self, version: int):
            self['custom']['lmp_version'] = version

        def apps(self):
            apps = self['custom'].get('docker_compose_apps')
            if not apps:
                raise Exception('Apps are NOT present in the given Target: {}'.format(self.name))

            for app_name, app_desc in apps.items():
                yield app_name, app_desc['uri']

        def has_apps(self):
            apps = self['custom'].get('docker_compose_apps')
            return apps is not None and len(apps) > 0

        def _set_apps_commit_hash(self):
            self._apps_commit_hash = None
            if self.apps_uri:
                uri_components = self.apps_uri.split('@')
                if len(uri_components) == 2:
                    self._apps_commit_hash = uri_components[1]

        def __getitem__(self, item):
            return self.json[item]

    class Release(NamedTuple):
        lmp_version: int
        yocto_version: str

        @classmethod
        def parse(cls, release_info: dict) -> 'Release':
            # VERSION="3.3.4-1147-84-270-gd10167f",
            # <yocto-version>-<commit-numb-after-tag>-<lmp-version>-<commit-numb-after-tag>-<abbreviated commit hash>
            version = release_info['VERSION'].strip('"')
            version_data = version.split('-')
            lmp_version = int(version_data[2]) if len(version_data) > 2 else 0
            yocto_version = version_data[0] if len(version_data) >= 1 else None
            return cls(lmp_version, yocto_version)

    def __init__(self, factory: str, token: str,
                 factory_api_base_url='https://api.foundries.io'):
        factory_resource = 'ota/factories/'
        targets_resource = 'targets/'

        self._auth_headers = {'osf-token': token}
        self._token = token
        self.factory = factory
        self.api_base_url = factory_api_base_url

        self._targets_endpoint = os.path.join(self.api_base_url, factory_resource, factory, targets_resource)

    @property
    def targets_endpoint(self):
        return self._targets_endpoint

    def get_targets(self, target_names: list):
        # TODO: add support of GETing a single resource/item from collection
        # targets_endpoint = http_get(os.path.join(self.targets_endpoint, target_name), headers=self._auth_headers)
        targets = self._get_targets()

        res_targets = []
        for target_name, target in targets.items():
            if target_name in target_names:
                res_targets.append(self.Target(target_name, target))
        return res_targets

    def get_target(self, target_name):
        return self.Target(target_name, self._get_target(target_name))

    def get_targets_by_version(self, version):
        res_targets = []
        targets = self._get_targets()
        for target_name, target in targets.items():
            custom = target.get('custom')
            if not custom:
                continue
            if custom.get('version', '') == version and custom.get('targetFormat', 'NONE') == 'OSTREE':
                res_targets.append(self.Target(target_name, target))

        return res_targets

    def get_target_system_image(self, target: Target, out_dir: str, progress: Progress, format=".wic"):
        # https://api.foundries.io/projects/<factory>/lmp/builds/<build-numb>/runs/<machine>/<image-name>-<machine>.wic.gz

        image_base_url = target['custom']['origUri'] if 'origUri' in target['custom'] else target['custom']['uri']
        image_machine = target['custom']['hardwareIds'][0]
        image_filename = target['custom']['image-file']

        base_url = image_base_url.replace('https://ci.foundries.io', self.api_base_url)
        if format == ".wic":
            image_url = os.path.join(base_url, 'runs', image_machine, image_filename)
        elif format == ".ota-ext4":
            image_filename = image_filename.replace('wic.gz', 'ota-ext4.gz')
            image_url = os.path.join(base_url, 'runs', image_machine, "other", image_filename)
        else:
            raise Exception('Unsupported system image format: ' + format)

        image_file_path = os.path.join(out_dir, image_filename)
        extracted_image_file_path = image_file_path.rstrip('.gz')

        p = Progress(2, progress)
        if not os.path.exists(extracted_image_file_path):
            logger.info('Downloading Target system image...; Target: {}, image: {}'
                        .format(target.name, image_filename))

            image_resp = requests.get(image_url, headers=self._auth_headers)
            image_resp.raise_for_status()
            with open(image_file_path, 'wb') as image_file:
                for data_chunk in image_resp.iter_content(chunk_size=65536):
                    image_file.write(data_chunk)
            p.tick()
            logger.info('Extracting Target system image: {}'.format(image_file_path))
            subprocess.check_call(['gunzip', '-f', image_file_path])
        else:
            logger.info('Target system image has been already downloaded: {}'.format(extracted_image_file_path))

        p.tick(complete=True)
        return extracted_image_file_path

    def get_target_release_info(self, target: Target):
        image_base_url = target['custom']['origUri'] if 'origUri' in target['custom'] else target['custom']['uri']
        base_url = image_base_url.replace('https://ci.foundries.io', self.api_base_url)
        image_machine = target['custom']['hardwareIds'][0]
        os_release_url = os.path.join(base_url, 'runs', image_machine, 'os-release')
        release_info = self.Release(0, '')
        try:
            release_resp = http_get(os_release_url, headers=self._auth_headers)
            release_info = self.Release.parse(dict([line.split('=') for line in release_resp.content.decode().splitlines()]))
        except Exception as exc:
                logger.error(f"Failed to get info about Target's LmP release; target: {target.name},"
                             " err: " + str(exc))
        return release_info

    def _get_targets(self):
        target_resp = http_get(self.targets_endpoint, headers=self._auth_headers)
        resp = target_resp.json()
        # A temporary workaround to switch from old format (a TUF compliant signed targets) to a new
        # format (a simple dictionary of targets).  Will be removed after an ota-lite change.
        targets = resp.get('signed', {}).get('targets', None)
        if targets is None:
            targets = resp
        # end of workaround
        return targets

    def _get_target(self, target_name):
        target_resp = http_get(self.targets_endpoint + target_name + '/', headers=self._auth_headers)
        return target_resp.json()
