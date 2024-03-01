#!/usr/bin/python3
#
# Copyright (c) 2019 Foundries.io
# SPDX-License-Identifier: BSD-3-Clause
#
import argparse
import logging
import json
import os
import subprocess
import urllib.request

from copy import deepcopy
from helpers import fio_dnsbase
from tag_manager import TagMgr

logging.basicConfig(level='INFO')
fh = logging.FileHandler('/archive/customize-target.log')
fh.setFormatter(logging.getLogger().handlers[0].formatter)
logging.getLogger().addHandler(fh)


def git_hash(gitdir):
    return subprocess.check_output(
        ['git', 'log', '-1', '--format=%H'], cwd=gitdir
    ).strip().decode()


def targets_from_api(factory):
    """ When we are called to create the installed_targets file, we'll
    We need to get the targets from the API so that we can help find the
       current docker-apps.
    """
    base = fio_dnsbase()
    url = f'https://api.{base}/ota/repo/{factory}/api/v1/user_repo/targets.json'
    try:
        with open('/secrets/osftok') as f:
            token = f.read().strip()
    except FileNotFoundError:
        logging.warning('osftok not found, assuming a simulator build')
        return {}

    req = urllib.request.Request(url, headers={'OSF-TOKEN': token})
    with urllib.request.urlopen(req, timeout=15) as response:
        data = json.load(response)
        return data['signed']['targets']


def merge(targets_json, target_name, lmp_manifest_sha, arch, image_name,
          machine, factory, ota_lite_tag, meta_subscriber_overrides_sha, lmp_ver):
    with open(targets_json) as f:
        data = json.load(f)

    changed = False

    try:
        targets = data['targets']
    except KeyError:
        logging.info('Assuming installed_versions file')
        # have a dict: ostree-hash: target-name, convert to a target
        name, version = target_name.rsplit('-', 1)
        machine, _ = name.split('-lmp', 1)
        data = {
            v: {
                'hashes': {'sha256': k},
                'is_current': True,
                'custom': {
                    'targetFormat': 'OSTREE',
                    'name': name,
                    'version': version,
                    'hardwareIds': [machine],
                }
            } for k, v in data.items()
        }
        targets = targets_from_api(factory)
        targets.update(data)
        changed = True

    tagmgr = TagMgr(ota_lite_tag)
    logging.info('Target is: %r', targets[target_name])
    logging.info('Doing Target tagging for: %s', tagmgr)

    updates = []
    for idx, (tgt_tag, apps_tag) in enumerate(tagmgr.tags):
        tgt = targets[args.target_name]
        tgt['custom']['lmp-ver'] = lmp_ver
        tgt['custom']['lmp-manifest-sha'] = lmp_manifest_sha
        tgt['custom']['arch'] = arch
        tgt['custom']['image-file'] = '{}-{}.wic.gz'.format(image_name, machine)
        if meta_subscriber_overrides_sha:
            tgt['custom']['meta-subscriber-overrides-sha'] = meta_subscriber_overrides_sha
        if idx:
            tgt = deepcopy(tgt)
            targets[args.target_name + '-%d' % idx] = tgt
            changed = True
        if tgt_tag:
            tgt['custom']['tags'] = [tgt_tag]
            changed = True
        updates.append({
            'ver': int(tgt['custom']['version']),
            'tag': apps_tag,
            'tgt': tgt,
            'prev': None,
        })

    # Now find the previous version of each target
    for tgt in targets.values():
        for cur in updates:
            if tgt['custom'].get('name') == cur['tgt']['custom']['name']:
                tag = cur['tag']
                match_tag = not tag or tag in tgt['custom'].get('tags', [])
                tgt_ver = int(tgt['custom']['version'])
                prev_ver = 0
                if cur['prev']:
                    prev_ver = int(cur['prev']['custom']['version'])
                if match_tag and tgt_ver > prev_ver and tgt_ver < cur['ver']:
                    cur['prev'] = tgt

    for u in updates:
        if u['prev']:
            logging.info('Prev is: %r', u['prev'])
            apps = u['prev']['custom'].get('docker_compose_apps')
            if apps:
                logging.info('Updating build to have compose apps: %r', apps)
                u['tgt']['custom']['docker_compose_apps'] = apps
                sha = u['prev']['custom'].get('containers-sha')
                if sha:
                    u['tgt']['custom']['containers-sha'] = sha
                apps_uri = u['prev']['custom'].get('origUriApps')
                if apps_uri:
                    u['tgt']['custom']['origUriApps'] = apps_uri
                else:
                    u['tgt']['custom']['origUriApps'] = u['prev']['custom']['uri']
                fetched_apps = u['prev']['custom'].get('fetched-apps')
                if fetched_apps:
                    u['tgt']['custom']['fetched-apps'] = fetched_apps
                changed = True

    if changed:
        logging.info('Target has changed, saving changes')
        with open(args.targets_json, 'w') as f:
            json.dump(data, f, indent=2)


def get_args():
    parser = argparse.ArgumentParser(
        '''Do LMP customiziations of the current build target. Including
           copying Compose Apps defined in the previous build target.''')

    parser.add_argument('run_url')
    parser.add_argument('factory')
    parser.add_argument('ota_lite_tag')
    parser.add_argument('machine')
    parser.add_argument('image_name')
    parser.add_argument('image_arch')
    parser.add_argument('lmp_ver')

    parser.add_argument('targets_json')
    parser.add_argument('target_name')

    parser.add_argument('--manifest-repo',
                        default=os.environ.get('MANIFEST_REPO', '/srv/oe/.repo/manifests'))
    parser.add_argument('--meta-sub-overrides-repo',
                        default=os.environ.get('META_SUB_OVERRIDES_REPO', '/srv/oe/layers/meta-subscriber-overrides'))

    return parser.parse_args()


if __name__ == '__main__':
    args = get_args()
    os.environ["H_RUN_URL"] = args.run_url  # allows fio_dnsbase helper to function

    if os.path.exists(args.meta_sub_overrides_repo):
        overrides_sha = git_hash(args.meta_sub_overrides_repo)
    else:
        logging.info("meta-subscriber-overrides layer/repo wasn't fetched")
        overrides_sha = None
    merge(args.targets_json, args.target_name, git_hash(args.manifest_repo),
          args.image_arch, args.image_name, args.machine, args.factory,
          args.ota_lite_tag, overrides_sha, args.lmp_ver)
