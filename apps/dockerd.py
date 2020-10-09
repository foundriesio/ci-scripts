# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import os
import time
import logging
import tempfile
import shutil
import subprocess


logger = logging.getLogger(__name__)


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
    def __init__(self, dst_dir: str, graphdriver='overlay2', output_logs=False):
        self.data_root = dst_dir
        self._graphdriver = graphdriver

        self.cmd = 'dockerd'
        self.host = 'unix:///tmp/run/docker-device.sock'
        self.pid = '/tmp/run/docker-device.pid'
        self._output_logs = output_logs

    def __enter__(self):
        self._containerd = ContainerDaemon().__enter__()
        self.docker_dir = tempfile.mkdtemp()
        self.host = 'unix://{}/docker-device.sock'.format(self.docker_dir)
        self.pid = '{}/docker-device.pid'.format(self.docker_dir)

        logger.info("Starting docker daemon...")
        cmd = [self.cmd, '-H', self.host, '-p', self.pid,
                                          '--storage-driver', self._graphdriver,
                                          '--data-root', self.data_root,
                                          '--containerd', self._containerd.address,
                                          '--experimental']

        if self._output_logs:
            self._process = subprocess.Popen(cmd)
        else:
            self._process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        # hack, let dockerd some time to start
        time.sleep(2)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._process.terminate()
        self._process.wait(timeout=60)

        shutil.rmtree(self.docker_dir)
        self._remove_non_image_data()
        logger.info("Docker daemon has been stopped")
        self._containerd.__exit__(exc_type, exc_val, exc_tb)

    def _remove_non_image_data(self):
        data_subdirs = os.listdir(self.data_root)
        for dir in data_subdirs:
            if dir not in self._image_data_dirs():
                shutil.rmtree(os.path.join(self.data_root, dir), ignore_errors=True)

    def _image_data_dirs(self):
        return ['image', 'overlay2', self._graphdriver]
