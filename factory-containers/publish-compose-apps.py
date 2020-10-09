#!/usr/bin/python3
#
# Copyright (c) 2019 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import os
import sys
import tempfile
import shutil
import subprocess
import logging
import yaml
import argparse


from helpers import cmd, require_env, status
from compose_app_downloader import main as dump_app_images
from target_manager import create_target

logging.basicConfig(level='INFO')


def normalize_keyvals(params: dict, prefix=''):
    """Handles two types of docker-app params:
       1) traditional. eg:
          key: val
          returns data as is
       2) docker app nested. eg:
          shellhttp:
            port: 80
          returns dict: {shell.httpd: 80}
    """
    normalized = {}
    for k, v in params.items():
        assert type(k) == str
        if type(v) == str:
            normalized[prefix + k] = v
        elif type(v) == int:
            normalized[prefix + k] = str(v)
        elif type(v) == dict:
            sub = normalize_keyvals(v, prefix + k + '.')
            normalized.update(sub)
        else:
            raise ValueError('Invalid parameter type for: %r' % v)
    return normalized


def convert_docker_app(path: str):
    """Take a .dockerapp file to directory format.
       The file format isn't supported by docker-app 0.8 and beyond. Just
       split a 3 sectioned yaml file into its pieces
    """
    with open(path) as f:
        _, compose, params = yaml.safe_load_all(f)
    if params is None:
        params = {}
    os.unlink(path)
    path, _ = os.path.splitext(path)
    try:
        # this directory might already exist. ie the user has:
        # shellhttpd.dockerapp
        # shellhttpd/Dockerfile...
        os.rename(path, path + '.orig')  # just move out of the way
    except FileNotFoundError:
        pass
    os.mkdir(path)
    # We need to try and convert docker-app style parameters to parameters
    # that are compatible with docker-compose
    params = normalize_keyvals(params)
    compose_str = yaml.dump(compose)
    for k, v in params.items():
        # there are two things we have to replace:
        # 1) Things with no defaults - ie ports: 8080:${PORT}
        #    We need to make this ${PORT-<default>} if we can
        compose_str = compose_str.replace('${%s}' % k, '${%s-%s}' % (k, v))
        # 2) Things that are nested - ie foo.bar=12
        #    We have to make this foo_bar so compose will accept it
        if '.' in k:
            safek = k.replace('.', '_')
            status('Replacing parameter "%s" with "%s" for compatibility' % (
                   k, safek))
            compose_str = compose_str.replace('${' + k, '${' + safek)
    with open(os.path.join(path, 'docker-compose.yml'), 'w') as f:
        f.write(compose_str)
    status('Converted docker-compose for %s\n' % compose_str)


def convert_docker_apps():
    """Loop through all the .dockerapp files in a directory and convert them
       to directory-based docker-compose.yml friendly representations.
    """
    for p in os.listdir():
        if not p.endswith('.dockerapp'):
            continue
        if os.path.isfile(p):
            status('Converting .dockerapp file for: ' + p)
            convert_docker_app(p)


def publish(factory: str, tag: str, app_name: str) -> str:
    base = 'hub.foundries.io/' + factory + '/'
    app = base + app_name
    tagged = app + ':app-' + tag

    changed = False
    with open(os.path.join(app_name, 'docker-compose.yml')) as f:
        compose = yaml.safe_load(f)
        for name, svc in compose['services'].items():
            img = svc['image']
            if img.startswith(base):
                # this should be a container defined in this factory and
                # in its containers.git, so it should get pinned to ${TAG}
                # to work as expected
                parts = img.split(':')
                if len(parts) == 1:
                    status('Image pinned to latest: %s, updating to %s' % (
                           img, tag))
                    svc['image'] = img + ':' + tag
                    changed = True
                elif len(parts) == 2:
                    allowed = ['${TAG}', 'latest', tag]
                    if factory == 'lmp':
                        # the lmp containers repo pulls in fiotest which sets
                        # its tag to "postmerge" which is okay based on how
                        # we do tagging for that repo.
                        allowed.append('postmerge')
                    if parts[1] not in allowed:
                        sys.exit('Image pinned to %s should be ${TAG} or %s' % (
                                 parts[1], tag))
                    svc['image'] = parts[0] + ':' + tag
                    changed = True
                else:
                    sys.exit('Unexpected image value: ' + img)
    if changed:
        with open(os.path.join(app_name, 'docker-compose.yml'), 'w') as f:
            yaml.dump(compose, f)

    out = cmd('compose-publish', tagged, cwd=app_name, capture=True)
    # The publish command produces output like:
    # = Publishing app...
    # |-> app:  sha256:fc73321368c7a805b0f697a0a845470bc022b6bdd45a8b34
    # |-> manifest:  sha256:e15e3824fc21ce13815aecb0490d60b3a32
    # We need the manifest sha so we can pin it properly in targets.json
    needle = b'|-> manifest:  sha256:'
    sha = out[out.find(needle) + len(needle):].strip()
    return app + '@sha256:' + sha.decode()


def main(factory: str, tag: str, ota_lite_tag: str, platforms: str, sha: str, version: str, targets_json: str,
         app_preload_flag: str, app_dir=None):
    convert_docker_apps()
    apps = {}

    cur_work_dir = os.path.abspath(os.getcwd())
    if app_dir:
        os.chdir(app_dir)

    status('Searching for apps in {}'.format(os.path.abspath(os.getcwd())))
    for app in os.listdir():
        if app.endswith('.disabled'):
            continue
        if os.path.exists(os.path.join(app, 'docker-compose.yml')):
            status('Validating compose file for: ' + app)
            cmd('docker-compose', 'config', cwd=app)
            status('Publishing compose app for: ' + app)
            uri = publish(factory, tag, app)
            apps[app] = {'uri': uri}

    create_target(targets_json, version, apps, ota_lite_tag, sha)

    if app_preload_flag == '1':
        # ------ Dumping container images of all apps -----
        app_images_dir = '/var/cache/bitbake/app-images/' + sha
        if os.path.exists(app_images_dir):
            shutil.rmtree(app_images_dir, ignore_errors=True)

        os.makedirs(app_images_dir)

        status('Dumping container images of the published compose apps to ' + app_images_dir)

        prefixed_platforms = platforms.split(',')
        archs = []
        for platform in prefixed_platforms:
            archs.append(platform.split('/')[1])

        with tempfile.TemporaryDirectory() as tmp_dst_dir:
            dump_app_images(os.path.abspath(os.getcwd()), archs, tmp_dst_dir)
            for arch in archs:
                subprocess.check_call(['tar', '-cf', os.path.join(app_images_dir, '{}-{}.tar'.format(sha, arch)),
                                       '-C', os.path.join(tmp_dst_dir, arch), '.'])


        # ------------------------------------------------

    if app_dir:
        os.chdir(cur_work_dir)


def get_args():
    parser = argparse.ArgumentParser('''Publish Target Compose Apps''')
    parser.add_argument('-t', '--targets', help='Targets json file')
    args = parser.parse_args()
    return args


if __name__ == '__main__':
    args = get_args()
    factory, tag, ota_lite_tag, platforms, sha, build_number = \
        require_env('FACTORY', 'TAG', 'OTA_LITE_TAG',
                    'MANIFEST_PLATFORMS_DEFAULT', 'GIT_SHA', 'H_BUILD')
    main(factory, tag, ota_lite_tag, platforms, sha,
         build_number, args.targets,
         os.environ.get('DOCKER_COMPOSE_APP_PRELOAD', '0'), os.environ.get('COMPOSE_APP_ROOT_DIR'))
