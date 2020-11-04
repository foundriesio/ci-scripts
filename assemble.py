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
from math import ceil

from helpers import cmd
from apps.target_apps_fetcher import TargetAppsFetcher
from apps.fetch import ArchiveTargetAppsStore
from factory_client import FactoryClient

logger = logging.getLogger("System Image Assembler")


class WicImage:
    DockerDataRootDir = 'ostree/deploy/lmp/var/lib/docker/'
    InstalledTargetFile = 'ostree/deploy/lmp/var/sota/import/installed_versions'

    def __init__(self, wic_image_path: str, increase_bytes=None, extra_space=0.2):
        self._path = wic_image_path
        self._mnt_dir = os.path.join('/mnt', 'wic_image_p2')
        self._resized_image = False
        if increase_bytes:
            self._resize_wic_file(increase_bytes, extra_space)
            self._resized_image = True
        self.docker_data_root = os.path.join(self._mnt_dir, self.DockerDataRootDir)
        self.installed_target_filepath = os.path.join(self._mnt_dir, self.InstalledTargetFile)

    def __enter__(self):
        cmd('losetup', '-P', '-f', self._path)
        out = cmd('losetup', '-a', capture=True).decode()
        for line in out.splitlines():
            if self._path in line:
                self._loop_device = out.split(':', 1)[0]
                self._wic_device = out.split(':', 1)[0] + 'p2'
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
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        cmd('umount', self._mnt_dir)
        os.rmdir(self._mnt_dir)
        cmd('umount', '/dev')
        cmd('losetup', '-d', self._loop_device)

    def update_target(self, target_json):
        logger.info('Updating installed Target (aka `installed_versions`) for the given system image\n')
        with open(self.installed_target_filepath, 'w') as installed_target_file:
            target_json['is_current'] = True
            json.dump(target_json, installed_target_file, indent=2)

    def _resize_wic_file(self, increase_bytes: int, extra_space=0.2):
        bs = 1024
        increase_k = ceil((increase_bytes + increase_bytes * extra_space) / bs) + 1
        wic_k = ceil(os.stat(self._path).st_size / bs)
        logger.info('Extending the wic image; adding: {} bytes, asked {}'.format(increase_k * bs, increase_bytes))
        cmd('dd', 'if=/dev/zero', 'bs=' + str(bs), 'of=' + self._path,
            'conv=notrunc', 'oflag=append', 'count=' + str(increase_k),
            'seek=' + str(wic_k))

        fdsik_out = str(subprocess.check_output(['fdisk', '-l', self._path]))
        if fdsik_out.find('using GPT') != -1:
            subprocess.check_call(['sgdisk', '-e', self._path])
        subprocess.check_call(['parted', self._path, 'resizepart', '2', '100%'])


def copy_container_images_to_wic(target: FactoryClient.Target, app_image_dir: str, app_preload_dir: str,
                                 wic_image: str, token: str, apps_shortlist: list):
    target_app_store = ArchiveTargetAppsStore(app_image_dir)
    target.shortlist = apps_shortlist
    if not target_app_store.exist(target):
        logger.info('Container images have not been found, trying to obtain them...')
        apps_fetcher = TargetAppsFetcher(token, app_preload_dir)
        apps_fetcher.fetch_target_apps(target, apps_shortlist)
        apps_fetcher.fetch_apps_images()
        target_app_store.store(target, apps_fetcher.images_dir(target.name))

    # in kilobytes
    image_data_size = target_app_store.images_size(target)
    with WicImage(wic_image, image_data_size * 1024) as wic_image:
        target_app_store.copy(target, wic_image.docker_data_root)
        wic_image.update_target({target.name: target.json})


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
    parser.add_argument('-w', '--wic-tool', help='A path to WIC utility')

    parser.add_argument('-a', '--app-image-dir', help='A path to directory that contains app container images')
    parser.add_argument('-o', '--out-image-dir', help='A path to directory to put a resultant image to')
    parser.add_argument('-d', '--preload-dir', help='Directory to fetch/preload/output apps and images')

    parser.add_argument('-T', '--targets', help='A coma separated list of Targets to assemble system image for')

    parser.add_argument('-s', '--app-shortlist', help='A coma separated list of Target Apps'
                                                      ' to include into a system image', default=None)

    args = parser.parse_args()

    if args.targets:
        args.targets = args.targets.split(',')

    if args.app_shortlist:
        if not args.targets:
            logger.error('Argument `App Shortlist` can be used only if `Targets` argument is specified')
            parser.print_help()
            exit(1)

        if len(args.targets) > 1:
            logger.error('Argument `App Shortlist` can be used only if `Targets` argument includes a single element')
            parser.print_help()
            exit(1)
        args.app_shortlist = args.app_shortlist.split(',')

    return args


if __name__ == '__main__':
    exit_code = 0

    try:
        logging.basicConfig(format='%(asctime)s %(levelname)s: Image Assembler: %(module)s: %(message)s', level=logging.INFO)
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

        logger.info('Found {} Targets to assemble image for'.format(found_targets_number))
        for target in targets:
            logger.info('Assembling image for {}, shortlist: {}'.format(target.name, args.app_shortlist))
            image_file_path = factory_client.get_target_system_image(target, args.out_image_dir)
            copy_container_images_to_wic(target, args.app_image_dir, args.preload_dir,
                                         image_file_path, args.token, args.app_shortlist)
            archive_and_output_assembled_wic(image_file_path, args.out_image_dir)
    except Exception as exc:
        logger.error('Failed to assemble a system image: {}'.format(exc))
        exit_code = 1

    exit(exit_code)
