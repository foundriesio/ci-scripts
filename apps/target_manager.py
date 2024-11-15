# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: BSD-3-Clause
import datetime
import logging
import os
import json
from copy import deepcopy

from helpers import fio_dnsbase
from tag_manager import TagMgr


logger = logging.getLogger(__name__)


def create_target(targets_json, compose_apps, ota_lite_tag, git_sha, machines, platforms,
                  in_version=None, new_target_dest_file=None) -> dict:
    tagmgr = TagMgr(ota_lite_tag)
    logging.info('Doing Target tagging for: %s', tagmgr)
    dnsbase = fio_dnsbase()

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
            # 1. are OSTREE type
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
            # For example, in the following case we should just create one Target v65 for rpi3 based on its v64
            # targets:
            # rpi3-lmp-64:
            # 	custom:
            # 		version: 64
            # 		hwids: rpi3
            # 		tags: master
            # intel-lmp-63:
            # 	custom:
            # 		version: 63
            # 		hwids: intel
            # 		tags: master
            if int(target['custom']['version']) != latest_tag_version[tag]:
                logger.warning('Skipping Target creation: {}, corresponding latest parent Target has not been found'
                               .format(tagmgr.create_target_name(target, version, tag),
                                       tagmgr.create_target_name(target, str(latest_tag_version[tag]), tag)))
                continue

            # Do not create Targets with MACHINE architectures (aka hardware ID) on which the Compose Apps built
            # in the given build cannot run due to lack of compatible platform.
            # For example, in the following case we should just create Target v65 for rpi3, it doesn't make sense
            # to create Target v65 for intel since the Compose Apps built in the given build cannot be run on
            # x86_64, they can be run only on aarch64 MACHINEs
            # rpi3-lmp-64:
            # 	custom:
            # 		version: 64
            # 		hwids: aarch64
            # 		tags: master
            # intel-lmp-64:
            # 	custom:
            # 		version: 64
            # 		hwids: x86_64
            # 		tags: master
            #
            # factory_config.yml
            # containers:
            #   platforms:
            #    - arm64
            if not _can_apps_run_on_target_machine(target, platforms):
                logger.warning('Skipping Target creation: {};'
                               ' None of the container platforms are compatible with Target\'s architecture;'
                               ' Container platforms: {}, Machine: {}'.
                               format(tagmgr.create_target_name(target, version, tag),
                                      platforms, target['custom']['hardwareIds'][0]))
                continue

            target = deepcopy(target)
            tgt_name = tagmgr.create_target_name(target, version, tag)
            data['targets'][tgt_name] = target

            now = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
            target['custom']['createdAt'] = now
            target['custom']['updatedAt'] = now
            uri = target['custom'].get('uri')
            if uri and 'origUri' not in target['custom']:
                # 'origUri' refers to the LmP build that generated rootfs of a given Target.
                # if it's already set then it means that a previous Target was generated by a container build,
                # so no need to set/overwrite it, just use the previous Target value.
                target['custom']['origUri'] = uri
            if 'origUriApps' in target['custom']:
                del target['custom']['origUriApps']
            proj = os.environ['H_PROJECT']
            build = os.environ['H_BUILD']
            target['custom']['uri'] = f'https://ci.{dnsbase}/projects/{proj}/builds/{build}'

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


def _can_apps_run_on_target_machine(target, factory_containers_platforms):
    """ Checks if there is at least one container platform among configured in factory_config.yml:containers.platforms
        that is compatible with the given Target's architecture/hardware ID.
    """

    # map MACHINE's archs to compatible containers/Apps' platforms
    # e.g. 'arm64' and 'arm' containers can be run on 'aarch64' MACHINEs
    OEArchToAppPlatformsMap = {
        'aarch64': ['arm64', 'arm'],
        'x86_64': ['amd64', 'amd'],
        'arm': ['arm']
    }
    machine_arch = target['custom'].get('arch')
    # If MACHINE's arch or factory containers' platforms is missing just skip this verification
    # and create the given Target
    if machine_arch and factory_containers_platforms:
        # get a list of container platforms that are compatible with the given Target's architecture
        try:
            target_platforms = OEArchToAppPlatformsMap[machine_arch]
        except KeyError:
            return False

        # get an intersection of container platforms that are compatible with the given Target's architecture and
        # the platforms enabled/configured in factory_config.yml:containers.platforms
        # Compose Apps' images are built only for platforms that are configured
        # in factory_config.yml:containers.platforms, so we cannot create Target that refers to Compose Apps
        # that cannot be run on the Target's machine architecture
        compatible_and_enabled_platforms =\
            [value for value in target_platforms if value in factory_containers_platforms]
        if len(compatible_and_enabled_platforms) == 0:
            return False

    return True
