#
# Copyright (c) 2019 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import logging
import json
from copy import deepcopy

from tag_manager import TagMgr


logger = logging.getLogger(__name__)


def create_target(targets_json, compose_apps, ota_lite_tag, git_sha, in_version=None):
    tagmgr = TagMgr(ota_lite_tag)
    logging.info('Doing Target tagging for: %s', tagmgr)

    latest_targets = {x: {} for x in tagmgr.target_tags}

    with open(targets_json) as f:
        data = json.load(f)
        latest_version = -1
        for name, target in data['targets'].items():
            if target['custom']['targetFormat'] == 'OSTREE':
                ver = int(target['custom']['version'])
                latest_version = ver if latest_version < ver else latest_version
                tgt_tags = target['custom'].get('tags') or []
                for tag in tagmgr.intersection(tgt_tags):
                    hwid = target['custom']['hardwareIds'][0]
                    cur = latest_targets[tag].get(hwid)
                    if not cur or int(cur['custom']['version']) < ver:
                        latest_targets[tag][hwid] = target

    version = in_version
    if not version:
        version = str(latest_version + 1)

    logging.info('Latest targets for the given build number {}\n{}'.format(
                 version, json.dumps(latest_targets, ensure_ascii=True, indent=2)))

    new_target_counter = 0
    for tag, latest in latest_targets.items():
        for target in latest.values():
            target = deepcopy(target)
            tgt_name = tagmgr.create_target_name(target, version, tag)
            data['targets'][tgt_name] = target

            target['custom']['version'] = version
            if tag:
                target['custom']['tags'] = [tag]
            target['custom']['containers-sha'] = git_sha
            if compose_apps:
                target['custom']['docker_compose_apps'] = compose_apps
            elif 'docker_compose_apps' in target['custom']:
                del target['custom']['docker_compose_apps']
            if 'docker_apps' in target['custom']:
                del target['custom']['docker_apps']
            logging.info('New Target with {}\n{}'.
                         format(tgt_name, json.dumps(target, ensure_ascii=True, indent=2)))
            new_target_counter += 1

    with open(targets_json, 'w') as f:
        json.dump(data, f, indent=2)

    return new_target_counter > 0
