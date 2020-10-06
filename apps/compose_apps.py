# Copyright (c) 2019 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import logging
import os
import yaml

from helpers import cmd as cmd_exe, status


logger = logging.getLogger(__name__)


class ComposeApps:
    DisabledSuffix = '.disabled'

    class App:
        DockerComposeTool = 'docker-compose'
        ComposeFile = 'docker-compose.yml'

        @staticmethod
        def is_compose_app_dir(app_dir):
            return os.path.exists(os.path.join(app_dir, ComposeApps.App.ComposeFile))

        def __init__(self, name, app_dir, validate=False):
            if not self.is_compose_app_dir(app_dir):
                raise Exception('Compose App dir {} does not contain a compose file {}'
                                .format(app_dir, self.ComposeFile))
            self.name = name
            self.dir = app_dir
            self.file = os.path.join(self.dir, self.ComposeFile)

            if validate:
                self.validate()

            with open(self.file) as compose_file:
                self._desc = yaml.safe_load(compose_file)

        def validate(self):
            self._run_cmd('config')

        def services(self):
            return self['services'].items()

        def images(self):
            for _, service_cfg in self.services():
                yield service_cfg['image']

        def tag_images(self, tag, image_base_url, allowed_tags=['${TAG}', 'latest']):
            changed = False
            for _, service_cfg in self.services():
                image_url = service_cfg['image']
                if not image_url.startswith(image_base_url):
                    continue

                parts = image_url.split(':')
                if len(parts) == 1:
                    status('Image pinned to latest: %s, updating to %s' % (image_url, tag))
                    service_cfg['image'] = image_url + ':' + tag
                    changed = True
                elif len(parts) == 2:
                    if not (parts[1] in allowed_tags or parts[1] == tag):
                        raise Exception('Image pinned to %s should be ${TAG} or %s' % (parts[1], tag))
                    service_cfg['image'] = parts[0] + ':' + tag
                    changed = True
                else:
                    raise Exception('Unexpected image value: ' + image_url)

            if changed:
                with open(self.file, 'w') as compose_file:
                    yaml.dump(self._desc, compose_file)

        def publish(self, publish_tool, app_tag):
            out = cmd_exe(publish_tool, app_tag, cwd=self.dir, capture=True)
            # The publish command produces output like:
            # = Publishing app...
            # |-> app:  sha256:fc73321368c7a805b0f697a0a845470bc022b6bdd45a8b34
            # |-> manifest:  sha256:e15e3824fc21ce13815aecb0490d60b3a32
            # We need the manifest sha so we can pin it properly in targets.json
            needle = b'|-> manifest:  sha256:'
            sha = out[out.find(needle) + len(needle):].strip()
            return sha.decode()

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

