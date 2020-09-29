#!/usr/bin/python3
#
# Copyright (c) 2019 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import json
import os
import sys
import tempfile
import shutil
import subprocess
import logging
import yaml
import argparse

from copy import deepcopy

from helpers import cmd, require_env, status
from compose_app_downloader import main as dump_app_images

logging.basicConfig(level='INFO')


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


class TagMgr:
    def __init__(self):
        # Convert thinkgs like:
        #    tag1,tag2 -> [(tag1, tag1), (tag2, tag2)]
        #    tag1:blah,tag2 -> [(tag1, blah), (tag2, tag2)]
        self._tags = []
        for x in (os.environ.get('OTA_LITE_TAG') or '').split(','):
            parts = x.strip().split(':', 1)
            if len(parts) == 1 or parts[1] == '':
                self._tags.append((parts[0], parts[0]))
            else:
                self._tags.append((parts[0], parts[1]))

    def __repr__(self):
        return str(self._tags)

    def intersection(self, tags):
        if self._tags == [('', '')]:
            # Factory doesn't use tags, so its good.
            # This empty value is special and understood by the caller
            yield ''
        else:
            for t in tags:
                for target, parent in self._tags:
                    if t == parent:
                        yield target

    def create_target_name(self, target, version, tag):
        name = target['custom']['name'] + '-' + version
        if len(self._tags) == 1:
            return name
        # we have more than one tag - so we need something else to make
        # this dictionary key name unique:
        return name + '-' + tag

    @property
    def target_tags(self):
        """Return the list of tags we should produce Targets for."""
        return [x[0] for x in self._tags]


def create_target(targets_json, version, compose_apps):
    tagmgr = TagMgr()
    logging.info('Doing Target tagging for: %s', tagmgr)

    latest_tags = {x: {} for x in tagmgr.target_tags}

    with open(targets_json) as f:
        data = json.load(f)
        for name, target in data['targets'].items():
            if target['custom']['targetFormat'] == 'OSTREE':
                tgt_tags = target['custom'].get('tags') or []
                for tag in tagmgr.intersection(tgt_tags):
                    hwid = target['custom']['hardwareIds'][0]
                    cur = latest_tags[tag].get(hwid)
                    ver = int(target['custom']['version'])
                    if not cur or int(cur['custom']['version']) < ver:
                        latest_tags[tag][hwid] = target

    logging.info('Latest targets: %r', latest_tags)
    for tag, latest in latest_tags.items():
        for target in latest.values():
            target = deepcopy(target)
            tgt_name = tagmgr.create_target_name(target, version, tag)
            data['targets'][tgt_name] = target

            target['custom']['version'] = version
            if tag:
                target['custom']['tags'] = [tag]
            apps = {}
            target['custom']['containers-sha'] = os.environ['GIT_SHA']
            if compose_apps:
                target['custom']['docker_compose_apps'] = compose_apps
            elif 'docker_compose_apps' in target['custom']:
                del target['custom']['docker_compose_apps']
            logging.info('Targets with apps: %r', target)

    with open(targets_json, 'w') as f:
        json.dump(data, f, indent=2)


def main(factory: str, tag: str, platforms: str, sha: str, version: str, targets_json: str,
         app_preload_flag: str, app_dir=None):
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

    create_target(targets_json, version, apps)

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
    factory, tag, platforms, sha, build_number = require_env('FACTORY', 'TAG', 'MANIFEST_PLATFORMS_DEFAULT', 'GIT_SHA', 'H_BUILD')
    main(factory, tag, platforms, sha,
         build_number, args.targets,
         os.environ.get('DOCKER_COMPOSE_APP_PRELOAD', '0'), os.environ.get('COMPOSE_APP_ROOT_DIR'))
