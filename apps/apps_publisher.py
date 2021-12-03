# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import logging
import os
from tempfile import NamedTemporaryFile

from expandvars import expandvars

from apps.compose_apps import ComposeApps
from apps.docker_registry_client import DockerRegistryClient
from helpers import cmd as cmd_exe


logger = logging.getLogger(__name__)


class AppsPublisher:
    def __init__(self, factory, publish_tool: str, archs: [], registry_host=DockerRegistryClient.DefaultRegistryHost):
        self._factory = factory
        self._publish_tool = publish_tool
        self._archs = archs
        self._registry_host = registry_host

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
        for service_name, service_cfg in app.services():
            image_url_template = service_cfg.get('image')
            if not image_url_template:
                raise Exception('Mandatory element `image:` is missing in the app service config; app: {}, service: {}'
                                .format(app.name, service_name))
            image_url = expandvars(image_url_template)
            logger.info('Service image url: %s', image_url)
            if not image_url.startswith(self._registry_host) or \
                    (self._factory != 'lmp' and image_url.startswith(self._registry_host + "/lmp/")):
                # image url points to non-Foundries docker registry or to Foundries public Factory (aka lmp)
                continue
            if not image_url.startswith(self._image_base_url):
                raise Exception('Image url refers to an image that does not belong to the given Factory;'
                                ' url: {}, factory: {}'.format(image_url, self._factory))

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
        with NamedTemporaryFile(mode="w+") as f:
            cmd_exe(self._publish_tool, '-d', f.name, self._app_tagged_url, self._archs, cwd=app.dir)
            return app_base_url + '@' + f.read().strip()
