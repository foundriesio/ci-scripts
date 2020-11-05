# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import logging
import json
from copy import deepcopy

from tag_manager import TagMgr


logger = logging.getLogger(__name__)


def create_target(targets_json, compose_apps, ota_lite_tag, git_sha, machines,
                  in_version=None, new_target_dest_file=None) -> dict:
    # TODO: take into account containers.platforms, we cannot create a new Target with Apps
    # for machine that does not have matching platform in containers.platforms

    tagmgr = TagMgr(ota_lite_tag)
    logging.info('Doing Target tagging for: %s', tagmgr)

    latest_targets = {x: {} for x in tagmgr.target_tags}

    with open(targets_json) as f:
        data = json.load(f)
        latest_version = -1
        latest_tag_version = {}

        for name, target in data['targets'].items():
            hwid = target['custom']['hardwareIds'][0]
            ver = int(target['custom']['version'])
            latest_version = ver if latest_version < ver else latest_version
            # create new Targets based on existing Targets that
            # 1. are OSTREE type (TODO: it's redundant since we have only ostree Targets)
            # 2. matches currently defined MACHINES (target.hwid in MACHINES),
            #    use-case: machine was removed  just before the container build
            if target['custom']['targetFormat'] == 'OSTREE' and (hwid in machines if machines else True):
                tgt_tags = target['custom'].get('tags') or []
                for tag in tagmgr.intersection(tgt_tags):
                    cur = latest_targets[tag].get(hwid)
                    if not cur or int(cur['custom']['version']) < ver:
                        latest_targets[tag][hwid] = target
                        # The latest version across all hwid/machines per tag
                        if not latest_tag_version.get(tag) or ver > latest_tag_version[tag]:
                            latest_tag_version[tag] = ver

    version = in_version
    if not version:
        version = str(latest_version + 1)

    logger.info('Latest targets for the given build number {}\n{}'.format(
                 version, json.dumps(latest_targets, ensure_ascii=True, indent=2)))

    new_targets = {}
    for tag, latest in latest_targets.items():
        for target in latest.values():
            # Assumption/Policy is that the latest version should be same across all hwids/machines for a specific tag,
            # if it's not true for some parent Target then we skip creation of the new Target. It can be so
            # in the case if the expected version of the parent Target failed and for some reason we don't
            # want to create a new Target based on the latest available Target
            if int(target['custom']['version']) != latest_tag_version[tag]:
                logger.warning('Skipping Target creation: {}, corresponding latest parent Target has not been found'
                               .format(tagmgr.create_target_name(target, version, tag),
                                       tagmgr.create_target_name(target, str(latest_tag_version[tag]), tag)))
                continue
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
            logger.info('New Target with {}\n{}'.
                         format(tgt_name, json.dumps(target, ensure_ascii=True, indent=2)))
            new_targets[tgt_name] = target

    with open(targets_json, 'w') as f:
        json.dump(data, f, indent=2)

    if new_target_dest_file and len(new_targets) > 0:
        with open(new_target_dest_file, 'w') as f:
            json.dump(new_targets, f, indent=2)

    return new_targets
