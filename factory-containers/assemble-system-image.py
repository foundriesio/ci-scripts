#!/usr/bin/python3
#
# Copyright (c) 2019 Foundries.io
# SPDX-License-Identifier: Apache-2.0
#
import subprocess
import os
import json
import argparse
import logging
import tempfile
import base64
import contextlib
import shutil
from math import ceil

from helpers import cmd, http_get
from compose_app_downloader import dump_app_images


logger = logging.getLogger("System Image Assembler")
wic_tool = None


def _get_targets_from_api(factory: str, token: str):
    api_base_url = 'https://api.foundries.io/ota/repo/'
    targets_endpoint = 'api/v1/user_repo/targets.json'

    target_url = os.path.join(api_base_url, factory, targets_endpoint)
    target_resp = http_get(target_url, headers={'OSF-TOKEN': token})
    return target_resp.json()['signed']['targets']


def get_targets_from_api_by_build_numb(factory: str, build_num: str, token: str):
    logger.info('Fetching factory targets; Factory: {}, version: {}'.format(factory, build_num))
    targets = _get_targets_from_api(factory, token)
    res_targets = {}

    for target_name, target in targets.items():
        custom = target.get('custom')
        if not custom:
            continue

        if custom.get('version', '') == build_num and custom.get('targetFormat', 'NONE') == 'OSTREE':
            res_targets[target_name] = target
    return res_targets


def get_targets_from_api_by_targets(factory: str, target_names: list, token: str):
    logger.info('Fetching factory targets; Factory: {}, Targets: {}'.format(factory, target_names))
    targets = _get_targets_from_api(factory, token)
    res_targets = {}
    for target_name in target_names:
        if target_name in targets:
            res_targets[target_name] = targets[target_name]
    return res_targets


def get_system_image_from_ci(target: dict, token: str):
    # https://api.foundries.io/projects/<factory>/lmp/builds/<build-numb>/runs/<machine>/<image-name>-<machine>.wic.gz

    image_base_url = target['custom']['uri']
    image_machine = target['custom']['hardwareIds'][0]
    image_filename = target['custom']['image-file']

    base_url = image_base_url.replace('ci.foundries.io', 'api.foundries.io')
    image_url = os.path.join(base_url, 'runs', image_machine, image_filename)

    logger.info('Fetching {}...\n'.format(image_url))

    image_resp = http_get(image_url, headers={'OSF-TOKEN': token})
    with open(image_filename, 'wb') as image_file:
        for data_chunk in image_resp.iter_content(chunk_size=65536):
            image_file.write(data_chunk)

    subprocess.check_call(['gunzip', '-f', image_filename])
    return image_filename.rstrip('.gz')


def get_registry_jwt_token(registry_oauth_token, factory, repo, hub_creds):
    user_pass = '{}:{}'.format(hub_creds['Username'], hub_creds['Secret'])

    headers = {
        'Authorization': 'Basic ' + base64.b64encode(user_pass.encode()).decode()
    }

    params = {
        'service': 'registry',
        'scope': 'repository:{}/{}:pull'.format(factory, repo)
    }

    token_req = http_get(registry_oauth_token, headers=headers, params=params)
    return token_req.json()


def download_target_app(target: dict, token: str, app_root_dir: str):
    app_shortlist = target.get('app_shortlist')
    for app, app_desc in target['custom']['docker_compose_apps'].items():
        if app_shortlist and app not in app_shortlist:
            logger.info('Skipping downloading Compose App {}'.format(app))
            continue

        logger.info('Downloading Compose App {}...'.format(app))
        uri = app_desc['uri']
        uri_parts = uri.split('@')
        registry_host, factory, app = uri_parts[0].split('/')
        digest = uri_parts[1]

        registry_jwt_token = get_registry_jwt_token('https://hub.foundries.io/token-auth/', factory, app,
                                                    {'Username': 'ci-job', 'Secret': token})

        manifest_url = 'https://{}/v2/{}/{}/manifests/{}'.format(registry_host, factory, app, digest)
        logger.info('Pulling App manifest: {}'.format(manifest_url))
        manifest_resp = http_get(manifest_url,
                                     headers={'authorization': 'bearer {}'.format(registry_jwt_token['token']),
                                              'accept': 'application/vnd.oci.image.manifest.v1+json'})
        manifest = json.loads(manifest_resp.content)
        logger.info('Got App manifest')

        app_url = 'https://{}/v2/{}/{}/blobs/{}'.format(registry_host, factory, app, manifest['layers'][0]['digest'])
        logger.info('Pulling App archive: {}'.format(app_url))
        archive_resp = http_get(app_url, headers={'authorization': 'bearer {}'.format(registry_jwt_token['token'])})
        app_archive_file = os.path.join(app_root_dir, app + '.tgz')
        with open(app_archive_file, 'wb') as app_tgz:
            app_tgz.write(archive_resp.content)

        logger.info('Got {}'.format(app_archive_file))
        app_dir = os.path.join(app_root_dir, app)
        os.makedirs(app_dir, exist_ok=True)
        subprocess.check_call(['tar', '-xzf', app_archive_file, '-C', app_dir])
        logger.info('Compose App {} has been downloaded and extracted to {}'.format(app, app_dir))


def login_at_docker_registry(token, registry_host='hub.foundries.io'):
    login_process = subprocess.Popen(
        ['docker', 'login', registry_host, '--username=doesntmatter', '--password-stdin'],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    output = login_process.communicate(input=token.encode())[0]
    # this is kind of useless verification because login at hub.foundries.io is successful
    # for any value of username and/or password
    if -1 == (str(output)).find('Login Succeeded'):
        raise Exception('Failed to login at {}'.format('hub.foundries.io'))


def dump_apps_container_images(target: dict, containers_arch: str, app_image_tar: str, token: str):
    login_at_docker_registry(token)
    with tempfile.TemporaryDirectory() as tmp_docker_dir:
        with tempfile.TemporaryDirectory() as tmp_app_dir:
            download_target_app(target, token, tmp_app_dir)
            image_data_dir = dump_app_images(tmp_app_dir, [containers_arch], tmp_docker_dir)
            subprocess.check_call(['tar', '-cf', app_image_tar,
                                   '-C', image_data_dir[containers_arch], '.'])
            return int(subprocess.check_output(['du', '-sk', image_data_dir[containers_arch]]).split()[0].decode('utf-8'))


class WicImage:
    def __init__(self, wic_image_path: str, increase_bytes=None, extra_space=0.2):
        self._path = wic_image_path
        self._mnt_dir = os.path.join('/mnt', 'wic_image_p2')
        self._resized_image = False
        if increase_bytes:
            self._resize_wic_file(increase_bytes, extra_space)
            self._resized_image = True

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
        return os.path.join(self._mnt_dir, 'ostree/deploy/lmp')

    def __exit__(self, exc_type, exc_val, exc_tb):
        cmd('umount', self._mnt_dir)
        os.rmdir(self._mnt_dir)
        cmd('umount', '/dev')
        cmd('losetup', '-d', self._loop_device)

    def _resize_wic_file(self, increase_bytes: int, extra_space=0.2):
        bs = 1024
        increase_k = ceil((increase_bytes + increase_bytes * extra_space) / bs) + 1
        wic_k = ceil(os.stat(self._path).st_size / bs)
        logger.info('Adding %d bytes to wic size (asked %d)', increase_k * bs, increase_bytes)
        cmd('dd', 'if=/dev/zero', 'bs=' + str(bs), 'of=' + self._path,
            'conv=notrunc', 'oflag=append', 'count=' + str(increase_k),
            'seek=' + str(wic_k))

        fdsik_out = str(subprocess.check_output(['fdisk', '-l', self._path]))
        if fdsik_out.find('using GPT') != -1:
            subprocess.check_call(['sgdisk', '-e', self._path])
        subprocess.check_call(['parted', self._path, 'resizepart', '2', '100%'])


def copy_container_images_to_wic(target: dict, app_image_dir: str, wic_image: str, token: str):
    partition = '2'
    directory = '/ostree/deploy/lmp/var/lib/docker/'

    containers_sha = target['custom']['containers-sha']
    arch_map = {'aarch64': 'arm64', 'x86_64': 'amd64', 'arm': 'arm'}
    containers_arch = arch_map[target['custom']['arch']]

    app_shortlist = target.get('app_shortlist')
    if app_shortlist:
        apps_list = '_'.join(app_shortlist)
        app_image_tar_src = os.path.join(app_image_dir, containers_sha, '{}-{}-{}.tar'.
                                         format(containers_sha, containers_arch, apps_list))
    else:
        app_image_tar_src = os.path.join(app_image_dir, containers_sha,
                                         '{}-{}.tar'.format(containers_sha, containers_arch))

    # in kilobytes
    image_data_size = None
    if not os.path.exists(app_image_tar_src):
        logger.info('Container images have not been found, trying to obtain them...')
        os.makedirs(os.path.dirname(app_image_tar_src), exist_ok=True)
        image_data_size = dump_apps_container_images(target, containers_arch, app_image_tar_src, token)
    else:
        with tempfile.TemporaryDirectory() as tmp_image_data:
            # container images data have been already dumped and stored on NFS
            # TODO: store the image data size on NFS along with the tarball
            #  to avoid calling tar -xf <> to determine uncompressed image data size
            subprocess.check_call(['tar', '-xf', app_image_tar_src, '-C', tmp_image_data])
            image_data_size = int(subprocess.check_output(['du', '-sk', tmp_image_data]).split()[0].decode('utf-8'))

    with WicImage(wic_image, image_data_size * 1024) as ostree_deploy_root:
        docker_data_root = os.path.join(ostree_deploy_root, 'var/lib/docker')
        if os.path.exists(docker_data_root):
            # wic image was populated by container images data during LmP build
            # let's remove it and populate with the given images data
            shutil.rmtree(docker_data_root)

        os.makedirs(docker_data_root)
        logger.info('Copying container images of Target apps to Target WIC image: {} --> {}'
                    .format(app_image_tar_src, docker_data_root))
        subprocess.check_call(['tar', '-xf', app_image_tar_src, '-C', docker_data_root])


def update_installed_versions_on_wic_image(target_name: str, target: str, wic_image: str):
    installed_versions_filename = 'installed_versions'
    old_installed_versions_filename = 'installed_versions.old'
    partition = '2'
    installed_versions_in_wic_image = '/ostree/deploy/lmp/var/sota/import/' + installed_versions_filename

    target['is_current'] = True
    if target.get('app_shortlist'):
        del target['app_shortlist']
    installed_versions = {target_name: target}

    with open(installed_versions_filename, 'w') as installed_versions_file:
        json.dump(installed_versions, installed_versions_file, indent=2)

    installed_versions_dst_path = '{}:{}{}'.format(wic_image, partition, installed_versions_in_wic_image)
    subprocess.check_call([wic_tool, 'cp', installed_versions_dst_path, old_installed_versions_filename])

    with open(old_installed_versions_filename, 'r') as f:
        old_version = json.load(f)

    logger.info('Updating `installed_versions` for the given system image\n')
    logger.info('From\n{}'.format(json.dumps(old_version, ensure_ascii=True, indent=2)))
    logger.info('To\n{}'.format(json.dumps(installed_versions, ensure_ascii=True, indent=2)))

    subprocess.check_call([wic_tool, 'rm', installed_versions_dst_path])
    subprocess.check_call([wic_tool, 'cp', installed_versions_filename, installed_versions_dst_path])


def archive_and_output_assembled_wic(wic_image: str, out_image_dir: str):
    logger.info('Gzip and move resultant WIC image to the specified destination folder: {}'.format(out_image_dir))
    os.makedirs(out_image_dir, exist_ok=True)
    subprocess.check_call(['gzip', wic_image])
    subprocess.check_call(['mv', wic_image + '.gz', out_image_dir])


def assemble_image_for_targets(targets: dict, app_image_dir: str, out_image_dir: str, token: str):
    for target_name, target in targets.items():
        logger.info('Got Target {}, processing it...'.format(target_name))
        wic_image = get_system_image_from_ci(target, token)
        copy_container_images_to_wic(target, app_image_dir, wic_image, token)
        update_installed_versions_on_wic_image(target_name, target, wic_image)
        archive_and_output_assembled_wic(wic_image, out_image_dir)


def get_args():
    parser = argparse.ArgumentParser('''Add container images to a system image''')

    parser.add_argument('-f', '--factory', help='Factory', default=os.environ.get('FACTORY'))
    parser.add_argument('-b', '--build-num', help='Build number', default=os.environ.get('H_BUILD'))
    parser.add_argument('-t', '--token-file', help='A file containing OSF token',
                        default=os.environ.get('TOKEN_FILE', '/secrets/osftok'))
    parser.add_argument('-w', '--wic-tool', help='A path to WIC utility', default=os.environ.get('WIC_TOOL'))
    parser.add_argument('-a', '--app-image-dir', help='A path to directory that contains app container images',
                        default=os.environ.get('APP_IMAGE_DIR'))
    parser.add_argument('-o', '--out-image-dir', help='A path to directory to put a resultant image to',
                        default=os.environ.get('OUT_IMAGE_DIR'))

    parser.add_argument('-T', '--targets', help='A coma separated list of Targets to assemble system image for',
                        default=os.environ.get('TARGETS'))

    parser.add_argument('-s', '--app-shortlist', help='A coma separated list of Target Apps'
                                                      ' to include into a system image',
                        default=os.environ.get('APP_SHORTLIST', ''))

    args = parser.parse_args()

    if args.factory is None:
        logger.error('Argument `Factory` is missing, specify it either as a command line argument'
                     ' or a FACTORY environment variable')
        parser.print_help()
        exit(1)

    if args.build_num is None and args.targets is None:
        logger.error('Both arguments `Build number` and `TARGETS` are missing, '
                     'specify one of them either as a command line argument or an H_BUILD environment variable')
        parser.print_help()
        exit(1)

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

    if args.token_file is None:
        logger.error('Argument `Token file` is missing, specify it either as a command line argument'
                     ' or a TOKEN_FILE environment variable')
        parser.print_help()
        exit(1)

    else:
        with open(args.token_file) as token_file:
            vars(args)['token'] = token_file.read().strip()

    if args.wic_tool is None:
        logger.error('Argument `WIC tool` is missing, specify it either as a command line argument'
                     ' or a WIC_TOOL environment variable')
        parser.print_help()
        exit(1)

    if args.app_image_dir is None:
        logger.error('Argument `App Image Dir` is missing, specify it either as a command line argument'
                     ' or a APP_IMAGE_DIR environment variable')
        parser.print_help()
        exit(1)

    if args.out_image_dir is None:
        logger.error('Argument `Out Image Dir` is missing, specify it either as a command line argument'
                     ' or a OUT_IMAGE_DIR environment variable')
        parser.print_help()
        exit(1)

    return args


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    args = get_args()
    wic_tool = args.wic_tool

    try:
        if args.targets:
            targets = get_targets_from_api_by_targets(args.factory, args.targets, args.token)
            err_msg = 'No Targets found; Factory: {}, input Target list: {}'.format(args.factory, args.targets)
            if args.app_shortlist:
                target_name = next(iter(targets))
                target_apps = targets[target_name]['custom']['docker_compose_apps'].keys()
                for app in args.app_shortlist:
                    if app not in target_apps:
                        logger.error('The shortlisted App `{}` is not listed in a given Target `{}`'.format(app, target_name))
                        exit(1)

                targets[target_name]['app_shortlist'] = args.app_shortlist
        else:
            targets = get_targets_from_api_by_build_numb(args.factory, str(args.build_num), args.token)
            err_msg = 'No Targets found; Factory: {}, Version/Build Number: {}'.format(args.factory, args.build_num)

        if len(targets) == 0:
            logger.warning(err_msg)
            exit(1)

        assemble_image_for_targets(targets, args.app_image_dir, args.out_image_dir, args.token)
    except Exception as exc:
        logger.exception(exc)
        exit(1)
