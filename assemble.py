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
from tempfile import TemporaryDirectory

from helpers import cmd, Progress
from apps.target_apps_fetcher import TargetAppsFetcher
from apps.target_apps_store import ArchiveTargetAppsStore
from apps.ostree_store import ArchOSTreeTargetAppsStore, OSTreeRepo
from factory_client import FactoryClient

logger = logging.getLogger("System Image Assembler")


class WicImage:
    ComposeAppsRootDir = 'ostree/deploy/lmp/var/sota/compose-apps/'
    DockerDataRootDir = 'ostree/deploy/lmp/var/lib/docker/'
    ComposeAppsRoot = 'ostree/deploy/lmp/var/sota/compose-apps'
    ComposeAppsTree = 'ostree/deploy/lmp/var/sota/compose-apps-tree'
    InstalledTargetFile = 'ostree/deploy/lmp/var/sota/import/installed_versions'

    def __init__(self, wic_image_path: str, increase_bytes=None, extra_space=0.2):
        self._path = wic_image_path
        self._mnt_dir = os.path.join('/mnt', 'wic_image_p2')
        self._resized_image = False
        if increase_bytes:
            self._resize_wic_file(increase_bytes, extra_space)
            self._resized_image = True
        self.compose_apps_root = os.path.join(self._mnt_dir, self.ComposeAppsRootDir)
        self.docker_data_root = os.path.join(self._mnt_dir, self.DockerDataRootDir)
        self.compose_apps_root = os.path.join(self._mnt_dir, self.ComposeAppsRoot)
        self.compose_apps_tree = os.path.join(self._mnt_dir, self.ComposeAppsTree)
        self.installed_target_filepath = os.path.join(self._mnt_dir, self.InstalledTargetFile)

    def __enter__(self):
        cmd('losetup', '-P', '-f', self._path)
        out = cmd('losetup', '-a', capture=True).decode()
        for line in out.splitlines():
            if self._path in line:
                self._loop_device = line.split(':', 1)[0]
                self._wic_device = line.split(':', 1)[0] + 'p2'
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
            'conv=notrunc', 'oflag=append', 'count=' + str(increase_k),
            'seek=' + str(wic_k))

        fdsik_out = str(subprocess.check_output(['fdisk', '-l', self._path]))
        if fdsik_out.find('using GPT') != -1:
            subprocess.check_call(['sgdisk', '-e', self._path])
        subprocess.check_call(['parted', self._path, 'resizepart', '2', '100%'])


def copy_container_images_to_wic(target: FactoryClient.Target, factory: str, ostree_repo_archive_dir: str,
                                 app_repo_dir, app_fetch_dir: str, wic_image: str, token: str, apps_shortlist: list,
                                 progress: Progress):

    p = Progress(2, progress)
    target_app_store = ArchOSTreeTargetAppsStore(factory, ostree_repo_archive_dir, app_repo_dir)
    target.shortlist = apps_shortlist
    if not target_app_store.exist(target):
        logger.info('Compose Apps haven\'t been found, fetching them...')
        apps_fetcher = TargetAppsFetcher(token, app_fetch_dir)
        if target_app_store.exist_branch(target):
            target_app_store.checkout(target, apps_fetcher.target_dir(target.name))
        apps_fetcher.fetch_target(target, force=True)
        target.apps_uri = target_app_store.store(target, apps_fetcher.target_dir(target.name))
    p.tick()

    with TemporaryDirectory(dir=os.getenv('HOME', '/root')) as tmp_tree_dir:
        # TODO: make use of the commit size generation functionality to determine a size to extend a wic image for
        logger.info('Building an ostree repo for the given Target...')
        os.makedirs(tmp_tree_dir, exist_ok=True)
        tmp_tree_repo = OSTreeRepo(tmp_tree_dir, 'bare', create=True)
        p.tick()
        target_app_store.copy(target, tmp_tree_repo)
        p.tick()

        with WicImage(wic_image, tmp_tree_repo.size_in_kbs() * 1024) as wic_image:
            logger.info('Removing previously preloaded Apps if any...')

            shutil.rmtree(wic_image.docker_data_root, ignore_errors=True)
            shutil.rmtree(wic_image.compose_apps_root, ignore_errors=True)
            shutil.rmtree(wic_image.compose_apps_tree, ignore_errors=True)
            p.tick()
            target_app_store.copy_and_checkout(target, wic_image.compose_apps_tree,
                                               wic_image.compose_apps_root, wic_image.docker_data_root)
            wic_image.update_target(target)
    p.tick()


def copy_container_images_from_archive_to_wic(target: FactoryClient.Target, app_image_dir: str, app_preload_dir: str,
                                              wic_image: str, token: str, apps_shortlist: list, progress: Progress):

    p = Progress(2, progress)
    target_app_store = ArchiveTargetAppsStore(app_image_dir)
    target.shortlist = apps_shortlist
    if not target_app_store.exist(target):
        logger.info('Container images have not been found, trying to obtain them...')
        apps_fetcher = TargetAppsFetcher(token, app_preload_dir)
        apps_fetcher.fetch_target_apps(target, apps_shortlist)
        apps_fetcher.fetch_apps_images()
        target_app_store.store(target, apps_fetcher.target_dir(target.name))
    p.tick()

    # in kilobytes
    image_data_size = target_app_store.images_size(target)
    with WicImage(wic_image, image_data_size * 1024) as wic_image:
        target_app_store.copy(target, wic_image.docker_data_root, wic_image.compose_apps_root)
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
    parser.add_argument('-ar', '--ostree-repo-archive-dir',
                        help='Path to a dir that contains an ostree repo archive with apps')
    parser.add_argument('-o', '--out-image-dir', help='A path to directory to put a resultant image to')
    parser.add_argument('-rd', '--repo-dir', help='Directory to extract an apps ostree repo to')
    parser.add_argument('-d', '--fetch-dir', help='Directory to fetch/preload/output apps and images')
    parser.add_argument('-T', '--targets', help='A coma separated list of Targets to assemble system image for')
    parser.add_argument('-s', '--app-shortlist', help='A coma separated list of Target Apps'
                                                      ' to include into a system image', default=None)
    parser.add_argument('-u', '--use-ostree', help='Enables an ostree repo usage for compose apps', default=None)
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
            image_file_path = factory_client.get_target_system_image(target, args.out_image_dir, subprog)

            if args.use_ostree and args.use_ostree == '1':
                copy_container_images_to_wic(target, args.factory, args.ostree_repo_archive_dir, args.repo_dir,
                                             args.fetch_dir, image_file_path, args.token, args.app_shortlist, subprog)
            else:
                copy_container_images_from_archive_to_wic(target, args.ostree_repo_archive_dir, args.fetch_dir,
                                                          image_file_path, args.token, args.app_shortlist, subprog)

            # Don't think its possible to have more than one tag at the time
            # we assemble, but the first tag will be the primary thing its
            # known as and also match what's in the target name.
            archive_dir = os.path.join(args.out_image_dir, target.tags[0])
            archive_and_output_assembled_wic(image_file_path, archive_dir)
            subprog.tick(complete=True)

    except Exception as exc:
        logger.error('Failed to assemble a system image: {}'.format(exc))
        exit_code = 1

    exit(exit_code)
