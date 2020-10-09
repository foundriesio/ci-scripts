# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import logging
from helpers import cmd as cmd_exe

from apps.compose_apps import ComposeApps
from apps.docker_registry_client import DockerRegistryClient


logger = logging.getLogger(__name__)


class AppsPublisher:
    def __init__(self, factory, publish_tool: str, registry_host=DockerRegistryClient.DefaultRegistryHost):
        self._publish_tool = publish_tool
        self._factory = factory

        self._image_base_url = '{}/{}'.format(registry_host, self._factory)
        self._allowed_tags = ['${TAG}', 'latest']
        if factory == 'lmp':
            # the lmp containers repo pulls in fiotest which sets
            # its tag to "postmerge" which is okay based on how
            # we do tagging for that repo.
            self._allowed_tags.append('postmerge')

    def publish(self, apps: ComposeApps, version: str):
        self.tag(apps, version)
        logger.info('Publishing Apps...')
        published_apps = {}
        [published_apps.update({app.name: {'uri': self.__publish(app, version)}}) for app in apps]
        return published_apps

    def tag(self, apps: ComposeApps, version: str):
        # TODO: Consider implementation of the "publish tool" in DockerRegistryClient
        # in this case we won't need the tagging step/changing image URIs in docker-compose.yml of each app
        logger.info('Tagging Apps...')
        [self.__tag(app, version) for app in apps]

    def __tag(self, app: ComposeApps.App, tag: str):
        changed = False
        for _, service_cfg in app.services():
            image_url = service_cfg['image']
            if not image_url.startswith(self._image_base_url):
                # TODO: verify if URL points to some other factory
                continue

            parts = image_url.split(':')
            if len(parts) == 1:
                logger.info('Image {} pinned to `latest`, updating to {}'.format(image_url, tag))
                service_cfg['image'] = image_url + ':' + tag
                changed = True
            elif len(parts) == 2:
                if not (parts[1] in self._allowed_tags or parts[1] == tag):
                    raise Exception('Image {} pinned to {}, can be {}'.format(image_url, parts[1], self._allowed_tags))

                logger.info('Image {} pinned to {}, updating to {}'.format(image_url, parts[1], tag))
                service_cfg['image'] = parts[0] + ':' + tag
                changed = True
            else:
                raise Exception('Unexpected image value: ' + image_url)

        if changed:
            app.save()

    def __publish(self, app: ComposeApps.App, tag: str):
        app_base_url = self._image_base_url + '/' + app.name
        self._app_tagged_url = app_base_url + ':app-' + tag
        # TODO: Consider implementation of the "publish tool" in DockerRegistryClient
        out = cmd_exe(self._publish_tool, self._app_tagged_url, cwd=app.dir, capture=True)
        # The publish command produces output like:
        # = Publishing app...
        # |-> app:  sha256:fc73321368c7a805b0f697a0a845470bc022b6bdd45a8b34
        # |-> manifest:  sha256:e15e3824fc21ce13815aecb0490d60b3a32
        # We need the manifest sha so we can pin it properly in targets.json
        needle = b'|-> manifest:  sha256:'
        sha = out[out.find(needle) + len(needle):].strip()
        app_hashed_uri = app_base_url + '@sha256:' + sha.decode()
        return app_hashed_uri
