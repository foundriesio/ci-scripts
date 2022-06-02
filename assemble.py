#!/usr/bin/python3
#
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0
#
import subprocess
import os
import json
import argparse
import logging
import shutil
from math import ceil
from time import sleep

from helpers import cmd, Progress
from apps.target_apps_fetcher import TargetAppsFetcher, SkopeAppFetcher
from factory_client import FactoryClient

logger = logging.getLogger("System Image Assembler")


class WicImage:
    ComposeAppsRootDir = 'ostree/deploy/lmp/var/sota/compose-apps/'
    DockerDataRootDir = 'ostree/deploy/lmp/var/lib/docker/'
    RestorableAppsRoot = 'ostree/deploy/lmp/var/sota/reset-apps'
    InstalledTargetFile = 'ostree/deploy/lmp/var/sota/import/installed_versions'

    def __init__(self, wic_image_path: str, increase_bytes=None, extra_space=0.2):
        self._path = wic_image_path
        self._mnt_dir = os.path.join('/mnt', 'wic_image_rootfs')
        self._installer_mount = None
        self._last_part = 2
        self._resized_image = False
        if increase_bytes:
            self._resize_wic_file(increase_bytes, extra_space)
            self._rootfs_bytes_increase = increase_bytes
            self._resized_image = True
        self.compose_apps_root = os.path.join(self._mnt_dir, self.ComposeAppsRootDir)
        self.docker_data_root = os.path.join(self._mnt_dir, self.DockerDataRootDir)
        self.restorable_apps_root = os.path.join(self._mnt_dir, self.RestorableAppsRoot)
        self.installed_target_filepath = os.path.join(self._mnt_dir, self.InstalledTargetFile)

    def __enter__(self):
        cmd('losetup', '-P', '-f', self._path)
        out = cmd('losetup', '-a', capture=True).decode()
        for line in out.splitlines():
            if self._path in line:
                self._loop_device = line.split(':', 1)[0]
                self._wic_device = line.split(':', 1)[0] + 'p' + str(self._last_part)
                break
        else:
            raise RuntimeError('Unable to find loop device for wic image')

        # containers don't see changes to /dev, so we have to hack around
        # this by basically mounting a new /dev. The idea was inspired by
        # this comment:
        #  https://github.com/moby/moby/issues/27886#issuecomment-257244027
        cmd('mount', '-t', 'devtmpfs', 'devtmpfs', '/dev')
        cmd('e2fsck', '-y', '-f', self._wic_device)

        if self._resized_image:
            cmd('resize2fs', self._wic_device)

        os.mkdir(self._mnt_dir)
        cmd('mount', self._wic_device, self._mnt_dir)

        installer = os.path.join(self._mnt_dir, 'rootfs.img')
        if os.path.exists(installer):
            if self._resized_image:
                self._resize_rootfs_img(installer, self._rootfs_bytes_increase)
            self._installer_mount = os.path.join('/mnt/installer_rootfs')
            os.mkdir(self._installer_mount)
            cmd('mount', '-oloop', installer, self._installer_mount)
            self.compose_apps_root = os.path.join(self._installer_mount, self.ComposeAppsRootDir)
            self.docker_data_root = os.path.join(self._installer_mount, self.DockerDataRootDir)
            self.restorable_apps_root = os.path.join(self._installer_mount, self.RestorableAppsRoot)
            self.installed_target_filepath = os.path.join(self._installer_mount, self.InstalledTargetFile)

        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self._installer_mount:
            cmd('umount', self._installer_mount)
            sleep(1)
            os.rmdir(self._installer_mount)
        cmd('umount', self._mnt_dir)
        os.rmdir(self._mnt_dir)
        cmd('umount', '/dev')
        cmd('losetup', '-d', self._loop_device)

    def update_target(self, target):
        logger.info('Updating installed Target (aka `installed_versions`) for the given system image\n')
        # make sure installed target dir path exists (e.g. wic-based installers)
        os.makedirs(os.path.dirname(self.installed_target_filepath), exist_ok=True)
        with open(self.installed_target_filepath, 'w') as installed_target_file:
            target.json['is_current'] = True
            json.dump({target.name: target.json}, installed_target_file, indent=2)

    def _resize_wic_file(self, increase_bytes: int, extra_space=0.2):
        bs = 1024
        increase_k = ceil((increase_bytes + increase_bytes * extra_space) / bs) + 1
        wic_k = ceil(os.stat(self._path).st_size / bs)
        logger.info('Extending the wic image; adding: {} bytes, asked {}'.format(increase_k * bs, increase_bytes))
        cmd('dd', 'if=/dev/zero', 'bs=' + str(bs), 'of=' + self._path,
            'conv=notrunc,fsync', 'oflag=append', 'count=' + str(increase_k),
            'seek=' + str(wic_k))

        parted_out = subprocess.check_output(['parted', self._path, 'print'])
        if parted_out.find(b'Partition Table: gpt') != -1:
            subprocess.check_call(['sgdisk', '-e', self._path])
        # save last partition # for resizing.  Example line for GPT:
        #  5      33.6MB  1459MB  1425MB  ext4         primary
        # and like this for msdos:
        #  2      50.3MB  688MB   638MB   primary  ext4
        # either way we can capture the first column as the last partition #
        # NOTE: use -3 index as parted_out will have 2x b'' items at the end
        self._last_part = int(parted_out.split(b'\n')[-3].split()[0])
        logger.info('last partition: %d' % self._last_part)
        subprocess.check_call(['parted', self._path, 'resizepart', str(self._last_part), '100%'])
        os.sync()

    def _resize_rootfs_img(self, path, increase_bytes: int):
        bs = 1024
        increase_k = ceil(increase_bytes / bs) + 1
        wic_k = ceil(os.stat(path).st_size / bs)
        logger.info('Extending the rootfs image; adding: {} bytes, asked {}'.format(increase_k * bs, increase_bytes))
        cmd('apk', 'add', 'coreutils')
        cmd('truncate', path, '-s', f'+{increase_k}K')
        cmd('e2fsck', '-y', '-f', path)
        cmd('resize2fs', path)


def _mk_parent_dir(path: str):
    if path[-1] == '/':
        path = path[:-1]
    path = os.path.dirname(path)
    os.makedirs(path, exist_ok=True)


def copy_compose_apps_to_wic(target: FactoryClient.Target, fetch_dir: str, wic_image: str, token: str,
                             apps_shortlist: list, progress: Progress):
    p = Progress(4, progress)
    apps_fetcher = TargetAppsFetcher(token, fetch_dir)
    apps_fetcher.fetch_target(target, shortlist=apps_shortlist, force=True)
    p.tick()
    apps_size_b = apps_fetcher.get_target_apps_size(target)
    p.tick()

    logger.info('Compose Apps require extra {} bytes of storage'.format(apps_size_b))
    with WicImage(wic_image, apps_size_b) as wic_image:
        if os.path.exists(wic_image.docker_data_root):
            # wic image was populated by container images data during LmP build (/var/lib/docker)
            # let's remove it and populate with the given images data
            logger.info('Removing existing preloaded app images from the system image')
            shutil.rmtree(wic_image.docker_data_root)
        else:
            # intel installer images won't have this directory
            _mk_parent_dir(wic_image.docker_data_root)


        if os.path.exists(wic_image.compose_apps_root):
            # wic image was populated by container images data during LmP build (/var/sota/compose-apps)
            # let's remove it and populate with the given images data
            logger.info('Removing existing preloaded compose apps from the system image')
            shutil.rmtree(wic_image.compose_apps_root)
        else:
            # intel installer images won't have this directory
            _mk_parent_dir(wic_image.compose_apps_root)

        # copy <fetch-dir>/<target-name>/apps/* to /var/sota/compose-apps/
        cmd('cp', '-a', apps_fetcher.apps_dir(target.name), wic_image.compose_apps_root)
        # copy <fetch-dir>/<target-name>/images/* to /var/lib/docker/
        cmd('cp', '-a', apps_fetcher.images_dir(target.name), wic_image.docker_data_root)

        p.tick()
        wic_image.update_target(target)
    p.tick()


def copy_restorable_apps_to_wic(target: FactoryClient.Target, wic_image: str, token: str, apps_shortlist: list,
                                fetch_dir: str, progress: Progress):
    p = Progress(4, progress)
    apps_fetcher = SkopeAppFetcher(token, fetch_dir)
    apps_fetcher.fetch_target(target, shortlist=apps_shortlist, force=True)
    p.tick()
    apps_size_b = apps_fetcher.get_target_apps_size(target)
    p.tick()

    logger.info('Restorable Apps require extra {} bytes of storage'.format(apps_size_b))
    with WicImage(wic_image, apps_size_b) as wic_image:
        if os.path.exists(wic_image.docker_data_root):
            # wic image was populated by container images data during LmP build (/var/lib/docker)
            # let's remove it and populate with the given images data
            logger.info('Removing existing preloaded app images from the system image')
            shutil.rmtree(wic_image.docker_data_root)

        if os.path.exists(wic_image.compose_apps_root):
            # wic image was populated by container images data during LmP build (/var/sota/compose-apps)
            # let's remove it and populate with the given images data
            logger.info('Removing existing preloaded compose apps from the system image')
            shutil.rmtree(wic_image.compose_apps_root)

        if os.path.exists(wic_image.restorable_apps_root):
            # wic image was populated by container images data during LmP build (/var/sota/reset-apps)
            # let's remove it and populate with the given images data
            logger.info('Removing existing preloaded app images from the system image')
            shutil.rmtree(wic_image.restorable_apps_root)

        cmd('cp', '-r', apps_fetcher.target_dir(target.name), wic_image.restorable_apps_root)
        p.tick()
        wic_image.update_target(target)
    p.tick()


def archive_and_output_assembled_wic(wic_image: str, out_image_dir: str):
    logger.info('Gzip and move resultant WIC image to the specified destination folder: {}'.format(out_image_dir))
    os.makedirs(out_image_dir, exist_ok=True)
    subprocess.check_call(['gzip', wic_image])
    subprocess.check_call(['mv', '-f', wic_image + '.gz', out_image_dir])


def get_args():
    parser = argparse.ArgumentParser('''Add container images to a system image''')

    parser.add_argument('-f', '--factory', help='Factory')
    parser.add_argument('-v', '--target-version', help='Target(s) version, aka build number')
    parser.add_argument('-t', '--token', help='A token')
    parser.add_argument('-o', '--out-image-dir', help='A path to directory to put a resultant image to')
    parser.add_argument('-d', '--fetch-dir', help='Directory to fetch/preload/output apps and images')
    parser.add_argument('-T', '--targets', help='A coma separated list of Targets to assemble system image for')
    parser.add_argument('-s', '--app-shortlist', help='A coma separated list of Target Apps'
                                                      ' to include into a system image', default=None)
    parser.add_argument('-at', '--app-type', help='Type of App to preload', default=None)
    args = parser.parse_args()

    if args.targets:
        args.targets = args.targets.split(',')

    if args.app_shortlist:
        args.app_shortlist = args.app_shortlist.split(',')

    return args


if __name__ == '__main__':
    exit_code = 0

    try:
        logging.basicConfig(format='%(asctime)s %(levelname)s: %(module)s: %(message)s', level=logging.INFO)
        args = get_args()

        factory_client = FactoryClient(args.factory, args.token)
        if args.targets:
            logger.info('Getting Targets for {}'.format(args.targets))
            targets = factory_client.get_targets(args.targets)
            err_msg = 'No Targets found; Factory: {}, input Target list: {}'.format(args.factory, args.targets)
        else:
            logger.info('Getting Targets of version {}'.format(args.target_version))
            targets = factory_client.get_targets_by_version(args.target_version)
            err_msg = 'No Targets found; Factory: {}, Version/Build Number: {}'.format(args.factory, args.target_version)

        found_targets_number = len(targets)
        if found_targets_number == 0:
            logger.warning(err_msg)
            exit(1)

        p = Progress(len(targets))
        logger.info('Found {} Targets to assemble image for'.format(found_targets_number))
        for target in targets:
            logger.info('Assembling image for {}, shortlist: {}'.format(target.name, args.app_shortlist))
            subprog = Progress(3, p)
            if not target.has_apps():
                logger.info("Target has no apps, skipping preload")
                subprog.tick(complete=True)
                continue
            image_file_path, release_info = factory_client.get_target_system_image(target, args.out_image_dir, subprog)

            if args.app_type == 'restorable' or (not args.app_type and release_info.lmp_version > 84):
                logger.info('Preloading Restorable Apps...')
                copy_restorable_apps_to_wic(target, image_file_path, args.token, args.app_shortlist, args.fetch_dir + "/restorable", subprog)

            logger.info('Preloading Compose Apps...')
            copy_compose_apps_to_wic(target, args.fetch_dir + "/compose", image_file_path, args.token, args.app_shortlist, subprog)

            # Don't think its possible to have more than one tag at the time
            # we assemble, but the first tag will be the primary thing its
            # known as and also match what's in the target name.
            archive_dir = os.path.join(args.out_image_dir, target.tags[0])
            archive_and_output_assembled_wic(image_file_path, archive_dir)
            subprog.tick(complete=True)

    except Exception as exc:
        logger.exception('Failed to assemble a system image')
        exit_code = 1

    exit(exit_code)
