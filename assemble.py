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

import requests
from math import ceil
from time import sleep
from typing import NamedTuple

from helpers import cmd, Progress
from apps.target_apps_fetcher import TargetAppsFetcher, SkopeAppFetcher
from factory_client import FactoryClient

logger = logging.getLogger("System Image Assembler")


def remount_dev():
    # containers don't see changes to /dev, so we have to hack around
    # this by basically mounting a new /dev. The idea was inspired by
    # this comment:
    #  https://github.com/moby/moby/issues/27886#issuecomment-257244027
    if getattr(remount_dev, 'called', None):
        # you can't call remount_dev dev a 2nd time without a umount, but
        # it also sometimes *fails* in between doing multiple target assemblies.
        # My guess is its something with dockerd getting spawned and stopped.
        # So just *try* to umount and hope for the best.
        subprocess.call(["umount", "/dev"])
    cmd('mount', '-t', 'devtmpfs', 'devtmpfs', '/dev')
    setattr(remount_dev, 'called', True)


def losetup(path: str) -> str:
    # losetup can be tricky to run in a container. Due to the issues with
    # /dev noted about in `remount_dev`, we periodically will have losetup
    # run like:
    #   bash-5.1# losetup -f /file
    #   losetup: /file: No such file or directory
    # However, losetup is giving misleading error message. strace will show the
    # real issue is that losetup creates new loop device, say loop2. However,
    # there's some kind of timing issue where /dev/loop2 doesn't always show
    # up, thus the "No such file or directory". When this happens, we need to
    # remount /dev in order to see the new device.
    try:
        # get the next available loop device
        loop_device = cmd('losetup', '-f', capture=True).decode().rstrip()
        cmd('losetup', '-P', loop_device, path)
    except subprocess.CalledProcessError:
        logger.error('losetup bug found, remounting /dev to work around')
        remount_dev()
        # get the next available loop device
        loop_device = cmd('losetup', '-f', capture=True).decode().rstrip()
        cmd('losetup', '-P', loop_device, path)

    # The -P in losetup scans for partitions and will create entries like:
    # /dev/loopXp1. Since these are new /dev entries, we have to remount /dev
    remount_dev()

    # make sure that the most recently created loop device represents a given system image (`path`)
    out = cmd('losetup', '-a', capture=True).decode()
    for line in out.splitlines():
        if path in line:
            if loop_device == line.split(':', 1)[0]:
                return loop_device
    raise RuntimeError(f'Unable to find loop device for {path}')


class ImageVolume:
    ComposeAppsRootDir = 'ostree/deploy/lmp/var/sota/compose-apps/'
    DockerDataRootDir = 'ostree/deploy/lmp/var/lib/docker/'
    RestorableAppsRoot = 'ostree/deploy/lmp/var/sota/reset-apps'
    InstalledTargetFile = 'ostree/deploy/lmp/var/sota/import/installed_versions'

    def __init__(self, image_path: str, increase_bytes=None, extra_space=0.2):
        self._path = image_path
        self._mnt_dir = os.path.join('/mnt', 'image_rootfs')
        self._installer_mount = None
        self._part_numb, self._gpt = self._get_last_part(self._path)
        logger.info(f'Detected last partition is {self._part_numb}, going to preload apps into it')
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
        self._loop_device = losetup(self._path)
        self._part_device = \
            self._loop_device if self._part_numb == 1 else f"{self._loop_device}p{self._part_numb}"

        cmd('e2fsck', '-y', '-f', self._part_device)

        if self._resized_image:
            cmd('resize2fs', self._part_device)

        os.mkdir(self._mnt_dir)
        cmd('mount', self._part_device, self._mnt_dir)

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
        cmd('losetup', '-d', self._loop_device)

    def update_target(self, target):
        logger.info('Updating installed Target (aka `installed_versions`) for the given system image\n')
        # make sure installed target dir path exists (e.g. wic-based installers)
        os.makedirs(os.path.dirname(self.installed_target_filepath), exist_ok=True)
        with open(self.installed_target_filepath, 'w') as installed_target_file:
            target.json['is_current'] = True
            json.dump({target.name: target.json}, installed_target_file, indent=2)

    @staticmethod
    def _get_last_part(path: str) -> tuple[int, str]:
        parted_out = subprocess.check_output(['parted', path, 'print'])
        is_gpt = False
        if parted_out.find(b'Partition Table: gpt') != -1:
            is_gpt = True
        # save last partition # for resizing and apps preloading.  Example line for GPT:
        #  5      33.6MB  1459MB  1425MB  ext4         primary
        # and like this for msdos:
        #  2      50.3MB  688MB   638MB   primary  ext4
        # either way we can capture the first column as the last partition #
        # NOTE: use -3 index as parted_out will have 2x b'' items at the end
        last_part = int(parted_out.split(b'\n')[-3].split()[0])
        return last_part, is_gpt

    def _resize_wic_file(self, increase_bytes: int, extra_space=0.2):
        bs = 1024
        increase_k = ceil((increase_bytes + increase_bytes * extra_space) / bs) + 1
        wic_k = ceil(os.stat(self._path).st_size / bs)
        logger.info('Extending the wic image; adding: {} bytes, asked {}'.format(increase_k * bs, increase_bytes))
        cmd('dd', 'if=/dev/zero', 'bs=' + str(bs), 'of=' + self._path,
            'conv=notrunc,fsync', 'oflag=append', 'count=' + str(increase_k),
            'seek=' + str(wic_k))
        if self._gpt:
            # The following command has to be executed to make `parted resizepart` work
            # in non-interactive mode ("Warning: Not all of the space available to...")
            subprocess.check_call(['sgdisk', '-e', self._path])
        subprocess.check_call(['parted', self._path, 'resizepart', str(self._part_numb), '100%'])
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


def copy_compose_apps_to_wic(target: FactoryClient.Target, fetch_dir: str, image_path: str,
                             token: str, apps_shortlist: list, progress: Progress):
    p = Progress(3, progress)
    apps_fetcher = TargetAppsFetcher(token, fetch_dir)
    apps_fetcher.fetch_target(target, shortlist=apps_shortlist, force=True)
    p.tick()
    apps_size_b = apps_fetcher.get_target_apps_size(target)

    logger.info('Compose Apps require extra {} bytes of storage'.format(apps_size_b))
    with ImageVolume(image_path, apps_size_b) as image_volume:
        p.tick()
        if os.path.exists(image_volume.docker_data_root):
            # wic image was populated by container images data during LmP build (/var/lib/docker)
            # let's remove it and populate with the given images data
            logger.info('Removing existing preloaded app images from the system image')
            shutil.rmtree(image_volume.docker_data_root)
        else:
            # intel installer images won't have this directory
            _mk_parent_dir(image_volume.docker_data_root)


        if os.path.exists(image_volume.compose_apps_root):
            # wic image was populated by container images data during LmP build (/var/sota/compose-apps)
            # let's remove it and populate with the given images data
            logger.info('Removing existing preloaded compose apps from the system image')
            shutil.rmtree(image_volume.compose_apps_root)
        else:
            # intel installer images won't have this directory
            _mk_parent_dir(image_volume.compose_apps_root)

        # copy <fetch-dir>/<target-name>/apps/* to /var/sota/compose-apps/
        cmd('cp', '-a', apps_fetcher.apps_dir(target.name), image_volume.compose_apps_root)
        # copy <fetch-dir>/<target-name>/images/* to /var/lib/docker/
        cmd('cp', '-a', apps_fetcher.images_dir(target.name), image_volume.docker_data_root)

        image_volume.update_target(target)
    p.tick(complete=True)


class AppsDesc(NamedTuple):
    dir: str
    size: int


def copy_restorable_apps_to_wic(target: FactoryClient.Target, image_path: str, apps: AppsDesc,
                                progress: Progress):
    p = Progress(2, progress)
    logger.info('Restorable Apps require extra {} bytes of storage'.format(apps.size))
    with ImageVolume(image_path, apps.size) as image_volume:
        p.tick()
        if os.path.exists(image_volume.docker_data_root):
            # wic image was populated by container images data during LmP build (/var/lib/docker)
            # let's remove it and populate with the given images data
            logger.info('Removing existing preloaded app images from the system image')
            shutil.rmtree(image_volume.docker_data_root)

        if os.path.exists(image_volume.compose_apps_root):
            # wic image was populated by container images data during LmP build (/var/sota/compose-apps)
            # let's remove it and populate with the given images data
            logger.info('Removing existing preloaded compose apps from the system image')
            shutil.rmtree(image_volume.compose_apps_root)

        if os.path.exists(image_volume.restorable_apps_root):
            # wic image was populated by container images data during LmP build (/var/sota/reset-apps)
            # let's remove it and populate with the given images data
            logger.info('Removing existing preloaded app images from the system image')
            shutil.rmtree(image_volume.restorable_apps_root)

        cmd('cp', '-r', apps.dir, image_volume.restorable_apps_root)
        image_volume.update_target(target)
    p.tick(complete=True)


def fetch_restorable_apps(target: FactoryClient.Target, dst_dir: str, shortlist: [str], token: str) -> AppsDesc:
    apps_fetcher = SkopeAppFetcher(token, dst_dir)
    apps_fetcher.fetch_target(target, shortlist=shortlist, force=True)
    return AppsDesc(apps_fetcher.target_dir(target.name), apps_fetcher.get_target_apps_size(target))


def archive_and_output_assembled_wic(wic_image: str, out_image_dir: str):
    logger.info('Gzip and move resultant system image to the specified destination folder: {}'.format(out_image_dir))
    subprocess.check_call(['bmaptool', 'create', wic_image, '-o', wic_image + '.bmap'])
    subprocess.check_call(['gzip', wic_image])
    subprocess.check_call(['mv', '-f', wic_image + '.gz', out_image_dir])
    subprocess.check_call(['mv', '-f', wic_image + '.bmap', out_image_dir])


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
        args.targets = [x.strip() for x in args.targets.split(',') if x]

    if args.app_shortlist:
        args.app_shortlist = [x.strip() for x in args.app_shortlist.split(',') if x]

    return args


if __name__ == '__main__':
    exit_code = 0
    fetched_apps = {}
    p = Progress(total=3)  # fetch apps, preload images, move apps to the archive dir

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
            p.tick(complete=True)
            exit(1)

        logger.info('Found {} Targets to assemble image for'.format(found_targets_number))
        apps_root_dir = args.fetch_dir + "/restorable"
        fetch_progress = Progress(len(targets), p)
        for target in targets:
            logger.info(f"Getting info about Target's Lmp release...")
            release_info = factory_client.get_target_release_info(target)
            if release_info.lmp_version > 0:
                logger.info(
                    f"Target's LmP version: {release_info.lmp_version}, yocto version: {release_info.yocto_version}")
            target.lmp_version = release_info.lmp_version
            if args.app_type == 'restorable' or (not args.app_type and release_info.lmp_version > 84):
                logger.info('Fetching Restorable Apps...')
                apps_desc = fetch_restorable_apps(target, apps_root_dir, args.app_shortlist, args.token)
                fetched_apps[target.name] = (apps_desc, os.path.join(args.out_image_dir, target.tags[0]))
            fetch_progress.tick()

        preload_progress = Progress(3 * len(targets) + len(fetched_apps), p)
        for target in targets:
            logger.info('Assembling image for {}, shortlist: {}'.format(target.name, args.app_shortlist))
            if not target.has_apps():
                logger.info("Target has no apps, skipping preload")
                preload_progress.tick(complete=True)
                continue

            try:
                image = factory_client.get_target_system_image(target, args.out_image_dir,
                                                               preload_progress)
            except requests.HTTPError as exc:
                if exc.response.status_code == 404:
                    # try to download `ota-ext4` image
                    logger.info("Target's system image in `.wic` format was not found,"
                                " trying to get an `.ota-ext4` image;"
                                " not found path: " + exc.response.url)
                    image = \
                        factory_client.get_target_system_image(target, args.out_image_dir,
                                                               preload_progress, format=".ota-ext4")
                else:
                    raise requests.exceptions.\
                        HTTPError('Failed to get {}: HTTP_{}\n{}'.format(exc.response.url,
                                                                         exc.response.status_code,
                                                                         exc.response.text))

            if target.name in fetched_apps:
                logger.info('Preloading Restorable Apps...')
                copy_restorable_apps_to_wic(target, image, fetched_apps[target.name][0], preload_progress)

            if target.name not in fetched_apps or target.lmp_version < 87:
                # Preload compose Apps if restorable one were not preloaded
                # or LmP version is lower than 87 (no early startup of restorable Apps,
                # so compose one should be preloaded too to make early startup working)
                logger.info('Preloading Compose Apps...')
                copy_compose_apps_to_wic(target, args.fetch_dir + "/compose", image, args.token,
                                         args.app_shortlist, preload_progress)

            # Don't think its possible to have more than one tag at the time
            # we assemble, but the first tag will be the primary thing its
            # known as and also match what's in the target name.
            dst_dir = os.path.join(args.out_image_dir, target.tags[0])
            os.makedirs(dst_dir, exist_ok=True)
            archive_and_output_assembled_wic(image, dst_dir)
            preload_progress.tick()

    except Exception as exc:
        logger.exception('Failed to assemble a system image')
        exit_code = 1

    for target, (apps_desc, dst_dir) in fetched_apps.items():
        os.makedirs(dst_dir, exist_ok=True)
        cmd('tar', '-cf', os.path.join(dst_dir, target + '-apps.tar'), '-C', apps_desc.dir, '.')

    p.tick(complete=True)
    exit(exit_code)
