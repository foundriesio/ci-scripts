import os
import logging
import subprocess
from typing import Optional

from helpers import Progress, http_get


logger = logging.getLogger(__name__)


class FactoryClient:
    class Target:
        OEArchToAppPlatformMap = {'aarch64': 'arm64', 'x86_64': 'amd64', 'arm': 'arm'}

        def __init__(self, target_name, target_json):
            self.name = target_name
            self.json = target_json

        @property
        def platform(self):
            return self.OEArchToAppPlatformMap[self['custom']['arch']]

        @property
        def sha(self):
            return self['custom']['containers-sha']

        @property
        def sha(self):
            return self['custom']['containers-sha']

        @property
        def shortlist(self):
            return self['custom'].get('shortlist')

        @shortlist.setter
        def shortlist(self, shortlist: []):
            self['custom']['shortlist'] = shortlist

        def apps(self):
            apps = self['custom'].get('docker_compose_apps')
            if not apps:
                raise Exception('Apps are NOT present in the given Target: {}'.format(self.name))

            for app_name, app_desc in apps.items():
                yield app_name, app_desc['uri']

        def __getitem__(self, item):
            return self.json[item]

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
        targets = self.__get_targets()

        res_targets = []
        for target_name, target in targets.items():
            if target_name in target_names:
                res_targets.append(self.Target(target_name, target))
        return res_targets

    def get_target(self, target_name):
        # TODO: add support of GETing a single resource/item from collection
        # targets_endpoint = http_get(os.path.join(self.targets_endpoint, target_name), headers=self._auth_headers)
        targets = self.__get_targets()
        return self.Target(target_name, targets.get(target_name))

    def get_targets_by_version(self, version):
        res_targets = []
        targets = self.__get_targets()
        for target_name, target in targets.items():
            custom = target.get('custom')
            if not custom:
                continue
            if custom.get('version', '') == version and custom.get('targetFormat', 'NONE') == 'OSTREE':
                res_targets.append(self.Target(target_name, target))

        return res_targets

    def get_target_system_image(self, target: Target, out_dir: str, progress: Progress):
        # https://api.foundries.io/projects/<factory>/lmp/builds/<build-numb>/runs/<machine>/<image-name>-<machine>.wic.gz

        image_base_url = target['custom']['uri']
        image_machine = target['custom']['hardwareIds'][0]
        image_filename = target['custom']['image-file']

        base_url = image_base_url.replace('https://ci.foundries.io', self.api_base_url)
        image_url = os.path.join(base_url, 'runs', image_machine, image_filename)

        image_file_path = os.path.join(out_dir, image_filename)
        extracted_image_file_path = image_file_path.rstrip('.gz')

        p = Progress(2, progress)

        if not os.path.exists(extracted_image_file_path):
            logger.info('Downloading Target system image...; Target: {}, image: {}'
                        .format(target.name, image_filename))

            image_resp = http_get(image_url, headers=self._auth_headers)
            with open(image_file_path, 'wb') as image_file:
                for data_chunk in image_resp.iter_content(chunk_size=65536):
                    image_file.write(data_chunk)
            p.tick()

            logger.info('Extracting Target system image: {}'.format(image_file_path))
            subprocess.check_call(['gunzip', '-f', image_file_path])
            p.tick()
        else:
            logger.info('Target system image has been already downloaded: {}'.format(extracted_image_file_path))

        return extracted_image_file_path

    def __get_targets(self):
        target_resp = http_get(self.targets_endpoint, headers=self._auth_headers)
        return target_resp.json()['signed']['targets']
