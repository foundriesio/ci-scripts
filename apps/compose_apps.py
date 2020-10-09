# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import logging
import os
import yaml

from helpers import cmd as cmd_exe
from apps.image_downloader import DockerDownloader


logger = logging.getLogger(__name__)


class ComposeApps:
    DisabledSuffix = '.disabled'

    class App:
        DockerComposeTool = 'docker-compose'
        ComposeFile = 'docker-compose.yml'

        @staticmethod
        def is_compose_app_dir(app_dir):
            return os.path.exists(os.path.join(app_dir, ComposeApps.App.ComposeFile))

        def __init__(self, name, app_dir, validate=False, image_downloader_cls=DockerDownloader):
            if not self.is_compose_app_dir(app_dir):
                raise Exception('Compose App dir {} does not contain a compose file {}'
                                .format(app_dir, self.ComposeFile))
            self.name = name
            self.dir = app_dir
            self.file = os.path.join(self.dir, self.ComposeFile)

            if validate:
                self.validate()

            self._image_downloader_cls = image_downloader_cls

            with open(self.file) as compose_file:
                self._desc = yaml.safe_load(compose_file)

        def validate(self):
            self._run_cmd('config')

        def services(self):
            return self['services'].items()

        def images(self):
            for _, service_cfg in self.services():
                yield service_cfg['image']

        def download_images(self, platform=None, docker_host='unix:///var/run/docker.sock'):
            downloader = self._image_downloader_cls(docker_host)
            for image in self.images():
                downloader.pull(image, platform)

        def save(self):
            with open(self.file, 'w') as compose_file:
                yaml.dump(self._desc, compose_file)

        def _run_cmd(self, cmd):
            cmd_exe(self.DockerComposeTool, '-f', self.file, cmd)

        def __getitem__(self, item):
            return self._desc[item]

    @property
    def apps(self):
        return self._apps

    @property
    def str(self):
        return ' '.join(app.name for app in self)

    def __init__(self, root_dir):
        self.root_dir = root_dir
        self._apps = []
        for app in os.listdir(self.root_dir):
            if app.endswith(self.DisabledSuffix):
                logger.info('App {} has been disabled, omitting it'.format(app))
                continue

            app_dir = os.path.join(self.root_dir, app)
            if not self.App.is_compose_app_dir(app_dir):
                logger.debug('An app dir {} is not Compose App dir'.format(app_dir))
                continue

            logger.debug('Found Compose App: '.format(app))
            self._apps.append(self.App(app, app_dir))

    def __iter__(self):
        return self._apps.__iter__()

    def __getitem__(self, item):
        return self._apps[item]

    def __len__(self):
        return len(self._apps)

    def validate(self):
        # throws exception on first invalid app
        [app.validate() for app in self]
