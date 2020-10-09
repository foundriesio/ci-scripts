# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import os
import logging
import subprocess


logger = logging.getLogger(__name__)


class ImageDownloader:
    def __init__(self, env):
        self._env = os.environ.copy()
        self._env.update(env)

    def pull(self, url, platform):
        cmd = self._get_cmd(url, platform)
        logger.info('Fetching image: {}'.format(cmd))
        subprocess.run(cmd.split(), check=True, stdout=None, stderr=None, env=self._env)

    def _get_cmd(self, platform: str, url: str):
        pass


class DockerDownloader(ImageDownloader):
    def __init__(self, dst_daemon_host):
        self.dst_daemon_host = dst_daemon_host

        super().__init__({'DOCKER_HOST': self.dst_daemon_host})

    def _get_cmd(self, url: str, platform=None):
        return 'docker pull --platform {} {}'.format(platform, url) if platform \
            else 'docker pull {}'.format(url)


class SkopeoDownloader(ImageDownloader):
    def __init__(self, dst_daemon_host):
        self._dst_daemon_host = dst_daemon_host

        super().__init__({'DOCKER_HOST': self._dst_daemon_host})

    def _get_cmd(self, url: str, platform=None):
        if -1 == url.find('@'):
            url_parts = url.split(':')
            sha = url_parts[1]
        else:
            url_parts = url.split('@')
            sha = url_parts[1].split(':')[1][:9]

        return 'skopeo --override-arch {} --override-os linux' \
               ' copy --dest-daemon-host {} docker://{} docker-daemon:{}:{}'.format(
            platform, self._dst_daemon_host, url, url_parts[0], sha) if platform else \
            'skopeo --override-os linux' \
               ' copy --dest-daemon-host {} docker://{} docker-daemon:{}:{}'.format(self._dst_daemon_host, url, url_parts[0], sha)
