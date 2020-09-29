#
# Copyright (c) 2019 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import logging
import json
from copy import deepcopy

from tag_manager import TagMgr


logger = logging.getLogger(__name__)


def create_target(targets_json, version, compose_apps, ota_lite_tag, git_sha):
    tagmgr = TagMgr(ota_lite_tag)
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
            target['custom']['containers-sha'] = git_sha
            if compose_apps:
                target['custom']['docker_compose_apps'] = compose_apps
            elif 'docker_compose_apps' in target['custom']:
                del target['custom']['docker_compose_apps']
            logging.info('Targets with apps: %r', target)

    with open(targets_json, 'w') as f:
        json.dump(data, f, indent=2)
