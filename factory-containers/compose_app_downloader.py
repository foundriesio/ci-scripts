#!/usr/bin/python3
#
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0
#

import yaml
import subprocess
import logging
import time
import os
import tempfile
import shutil
import argparse
import contextlib


logger = logging.getLogger(__name__)


class ComposeApp:
    def __init__(self, name, file_path):
        self.name = name
        self.file_path = file_path

        with open(self.file_path) as compose_file:
            self._composed_app = yaml.safe_load(compose_file)

    def services(self):
        return self._composed_app['services'].items()


class ContainerDaemon:
    def __init__(self):
        self.cmd = 'containerd'

    def __enter__(self):
        self._container_dir = tempfile.mkdtemp()

        self._root_dir = os.path.join(self._container_dir, 'root')
        os.mkdir(self._root_dir)

        self._state_dir = os.path.join(self._container_dir, 'state')
        os.mkdir(self._state_dir)

        self.address = os.path.join(self._container_dir, 'containerd.sock')

        logger.info("Starting containerd for docker daemon...")
        self._process = subprocess.Popen([self.cmd, '--address', self.address,
                                          '--root', self._root_dir,
                                          '--state', self._state_dir],
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # hack, let containerd some time to start
        time.sleep(2)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._process.terminate()
        self._process.wait(timeout=60)

        logger.info("Containerd daemon has been stopped")
        shutil.rmtree(self._container_dir)


class DockerDaemon:
    ImageDataDirs = ['overlay2', 'image']

    def __init__(self, dst_dir: str, containerd_addr: str):
        self.data_root = dst_dir
        self._containerd_addr = containerd_addr

        self.cmd = 'dockerd'
        self.host = 'unix:///tmp/run/docker-device.sock'
        self.pid = '/tmp/run/docker-device.pid'

    def __enter__(self):
        self.docker_dir = tempfile.mkdtemp()
        self.host = 'unix://{}/docker-device.sock'.format(self.docker_dir)
        self.pid = '{}/docker-device.pid'.format(self.docker_dir)

        logger.info("Starting docker daemon...")
        self._process = subprocess.Popen([self.cmd, '-H', self.host, '-p', self.pid,
                                          '--storage-driver', 'overlay2',
                                          '--data-root', self.data_root,
                                          '--containerd', self._containerd_addr,
                                          '--experimental'],
                                         stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # hack, let dockerd some time to start
        time.sleep(2)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._process.terminate()
        self._process.wait(timeout=60)

        shutil.rmtree(self.docker_dir)
        self._remove_non_image_data()
        logger.info("Docker daemon has been stopped")

    def _remove_non_image_data(self):
        data_subdirs = os.listdir(self.data_root)
        for dir in data_subdirs:
            if dir not in self.ImageDataDirs:
                shutil.rmtree(os.path.join(self.data_root, dir), ignore_errors=True)


class ImageDownloader:
    def __init__(self, env):
        self._env = os.environ.copy()
        self._env.update(env)

    def pull(self, platform, url):
        cmd = self._get_cmd(platform, url)
        logger.info('Fetching image: {}'.format(cmd))
        subprocess.run(cmd.split(), check=True, stdout=None, stderr=None, env=self._env)

    def _get_cmd(self, platform: str, url: str):
        pass

    def download_images(self, app: ComposeApp, platform, dst_dir: str):
        for service_name, service_cfg in app.services():
            logger.info('Copying image {} to {}'.format(service_cfg['image'], dst_dir))
            self.pull(platform, service_cfg['image'])


class DockerDownloader(ImageDownloader):
    def __init__(self, dst_daemon_host):
        self.dst_daemon_host = dst_daemon_host

        super().__init__({'DOCKER_HOST': self.dst_daemon_host})

    def _get_cmd(self, platform: str, url: str):
        return 'docker pull --platform {} {}'.format(platform, url)


class SkopeoDownloader(ImageDownloader):
    def __init__(self, dst_daemon_host):
        self._dst_daemon_host = dst_daemon_host

        super().__init__({'DOCKER_HOST': self._dst_daemon_host})

    def _get_cmd(self, platform, url: str):
        if -1 == url.find('@'):
            url_parts = url.split(':')
            sha = url_parts[1]
        else:
            url_parts = url.split('@')
            sha = url_parts[1].split(':')[1][:9]

        return 'skopeo --override-arch {} --override-os linux' \
               ' copy --dest-daemon-host {} docker://{} docker-daemon:{}:{}'.format(
            platform, self._dst_daemon_host, url, url_parts[0], sha)


# download app's images and store them in dockerd:overlay2 format
# they will NOT be stored in OCI or docker image format or flatten image rootfs/bundle
# the resultant file tree structure can be consumed solely by dockerd:overlay2 graph driver
@contextlib.contextmanager
def ComposeAppDownloader(arch, dst_dir, image_downloader_cls: ImageDownloader):
    with ContainerDaemon() as containerd:
        with DockerDaemon(dst_dir, containerd.address) as dockerd:
            downloader = image_downloader_cls(dockerd.host)

            def download_app(app: ComposeApp):
                for service_name, service_cfg in app.services():
                    logger.info('Copying image {} to {}'.format(service_cfg['image'], dst_dir))
                    downloader.pull(arch, service_cfg['image'])

            yield download_app


def ComposeAppList(compose_app_dir):
    for app in os.listdir(compose_app_dir):

        if app.endswith('.disabled'):
            logger.info('App {} has been disabled, omitting it'.format(app))
            continue

        compose_app_file = os.path.join(compose_app_dir, app, 'docker-compose.yml')
        if not os.path.exists(compose_app_file):
            logger.debug('A dir {} does not contain docker-compose.yml'.format(os.path.join(compose_app_dir, app)))
            continue

        logger.debug('Found compose app: '.format(app))
        yield ComposeApp(app, os.path.join(compose_app_dir, app, compose_app_file))


def dump_app_images(app_dir: str, archs: list, dst_dir: str):
    arch_to_dir = {}
    apps = list(ComposeAppList(app_dir))

    for arch in archs:
        dst_arch_dir = os.path.join(dst_dir, arch)
        if not os.path.exists(dst_arch_dir):
            os.makedirs(dst_arch_dir)

        logger.info("Downloading all images of {} architecture to {}".format(arch, dst_arch_dir))

        with ComposeAppDownloader(arch, dst_arch_dir, DockerDownloader) as download:
            for app in apps:
                logger.info('Downloading container images of {} to {}'.format(app.name, dst_arch_dir))
                download(app)

        arch_to_dir[arch] = dst_arch_dir
    return arch_to_dir


def main(app_dir: str, archs: list, dst_dir: str):
    logging.basicConfig(level=logging.INFO)

    arch_to_dir = {}
    try:
        arch_to_dir = dump_app_images(app_dir, archs, dst_dir)
    except Exception as exp:
        logger.error('Error occurred while trying to download app images: ' + str(exp))
    return arch_to_dir


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Downloader of Compose App images')
    parser.add_argument('--app-dir', help='a root directory of the target compose apps', required=True)
    parser.add_argument('--archs', help='a coma separated list of arch/platforms to download images for', required=True)
    parser.add_argument('--dst-dir', help='a root directory to dump app images to', required=True)
    args = parser.parse_args()

    main(args.app_dir, args.archs.split(','), args.dst_dir)
