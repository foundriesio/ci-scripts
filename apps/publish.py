#!/usr/bin/python3
#
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: BSD-3-Clause

import json
import logging
import argparse


from helpers import fio_dnsbase, status, jobserv_get
from apps.target_manager import create_target
from apps.compose_apps import ComposeApps
from apps.apps_publisher import AppsPublisher
from apps.docker_to_compose import convert_docker_apps
from apps.publish_manifest_lists import publish_manifest_lists


logger = logging.getLogger(__name__)


def get_layers_metadata(factory: str, ver: str, archs: []) -> dict:
    layers_meta = {}
    project = f"{factory}/lmp" if factory != "lmp" else "lmp"
    for a in archs:
        run_name = {"amd64": "build-amd64", "arm64": "build-aarch64", "arm": "build-armhf"}[a]
        status(f"Downloading layers metadata built by `{run_name}` run", prefix="=== ")
        layers_meta[a] = jobserv_get(f"/projects/{project}/builds/{ver}/runs/{run_name}/layers_meta.json")
    return layers_meta


def main(factory: str, sha: str, targets_json: str, machines: [], platforms: [], app_root_dir: str,
         publish_tool: str, apps_version: str, target_tag: str, target_version: str, new_targets_file: str):
    publish_manifest_lists()
    convert_docker_apps()
    status('Searching for Compose Apps in {}'.format(app_root_dir))
    apps = ComposeApps(app_root_dir)
    status('Found Compose Apps: {}'.format(apps.str))

    status('Compose Apps has been validated: {}'.format(apps.str))

    status('Downloading Apps\' layers metadata...')
    layers_meta = get_layers_metadata(factory, target_version, platforms)
    status('Apps\' layers metadata have been downloaded')

    reg_host = "hub." + fio_dnsbase()
    archs = ','.join(platforms) if platforms else ''
    apps_to_add_to_target = AppsPublisher(factory, publish_tool, archs, reg_host, layers_meta).publish(apps, apps_version)

    status('Creating Targets that refer to the published Apps; tag: {}, version: {}, machines: {}, platforms: {} '
           .format(target_tag, target_version, ','.join(machines) if machines else '[]',
                   ','.join(platforms) if platforms else '[]'))
    new_targets = create_target(targets_json, apps_to_add_to_target, target_tag, sha,
                                machines, platforms, target_version, new_targets_file)
    if len(new_targets) == 0:
        logger.error('Failed to create Targets for the published Apps')
        return 1

    return 0


def get_args():
    parser = argparse.ArgumentParser('''Publish Target Compose Apps''')
    parser.add_argument('-f', '--factory', help='Apps Factory')
    parser.add_argument('-t', '--targets', help='Targets json file')
    parser.add_argument('-m', '--machines', help='Factory machines', default=None)
    parser.add_argument('-a', '--platforms', help='Factory container platforms', default=None)
    parser.add_argument('-d', '--apps-root-dir', help='Compose Apps root directory')
    parser.add_argument('-p', '--publish-tool', help='A utility to be used for publishing (compose-ref)')
    parser.add_argument('-v', '--apps-version', help='Apps version which is by default is an abbreviated commit hash'
                                                     'of a given containers.git repo')
    parser.add_argument('-tt', '--target-tag', help='A tag to apply to Targets that will be created'
                                                    'by publishing the given apps')
    parser.add_argument('-s', '--git-sha', help='App/containers repo git sha')
    parser.add_argument('-tv', '--target-version', help='Version of Targets that will be created by a given call',
                        required=False, default=None)
    parser.add_argument('-o', '--new-targets-file', help='A file to put new Targets to')

    args = parser.parse_args()
    return args


if __name__ == '__main__':
    exit_code = 0
    try:
        logging.basicConfig(format='%(asctime)s %(levelname)s: %(module)s: %(message)s', level=logging.INFO)
        args = get_args()
        machines = [x.strip() for x in args.machines.split(',') if x.strip()] if args.machines else None
        platforms = None
        if args.platforms:
            # linux/amd64,linux/arm64  (list of archs/platforms defined in the old format)
            platforms = []
            platforms_old_format = args.platforms.split(',')
            for platform in platforms_old_format:
                platforms.append(platform.split('/')[1])

        exit_code = main(args.factory, args.git_sha, args.targets, machines, platforms,
                         args.apps_root_dir, args.publish_tool, args.apps_version, args.target_tag,
                         args.target_version, args.new_targets_file)
    except Exception as exc:
        logging.error('Failed to publish apps: {}'.format(exc))
        exit_code = 1

    exit(exit_code)
