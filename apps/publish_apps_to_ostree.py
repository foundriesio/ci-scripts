#!/usr/bin/python3
#
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import argparse
import logging
import json

from apps.target_publisher import TargetPublisher
from apps.ostree_store import ArchOSTreeTargetAppsStore
from factory_client import FactoryClient


def get_args():
    parser = argparse.ArgumentParser('''Publish Targets Apps and their images to OSTree repo''')
    parser.add_argument('-f', '--factory', help='Apps Factory')
    parser.add_argument('-a', '--token', help='Factory API Token, aka OSF Token')
    parser.add_argument('-c', '--cred-arch', help='Credentials archive used for auth at Treehub')
    parser.add_argument('-t', '--targets-file', help='A file containing all Factory Targets')
    parser.add_argument('-nt', '--targets-to-publish-file',
                        help='A file containing Targets apps and images of which to publish')
    parser.add_argument('-d', '--fetch-dir', help='Directory to fetch apps and images to')
    parser.add_argument('-o', '--repo-dir', help='Directory to extract an apps ostree repo to')
    parser.add_argument('-tr', '--treehub-repo-dir', help='Directory to create an ostree repo to push to Treehub')
    parser.add_argument('-ar', '--ostree-repo-archive-dir',
                        help='Path to a directory that an archive that contains an ostree repo with apps is located in')

    args = parser.parse_args()
    return args


if __name__ == '__main__':
    exit_code = 0
    try:
        logging.basicConfig(format='%(asctime)s %(levelname)s: %(module)s: %(message)s', level=logging.INFO)
        args = get_args()
        with open(args.targets_to_publish_file) as f:
            targets_json = json.load(f)

        targets_to_publish = []
        for target_name, target_json in targets_json.items():
            targets_to_publish.append(FactoryClient.Target(target_name, target_json))

        app_store = ArchOSTreeTargetAppsStore(args.factory, args.ostree_repo_archive_dir, args.repo_dir)
        publisher = TargetPublisher(args.factory, args.token, args.cred_arch, targets_to_publish, app_store,
                                    args.fetch_dir, args.treehub_repo_dir)

        publisher.fetch_targets()
        publisher.publish_targets()
        app_store.store_archive()

        # Update targets-created.json (hash of a commit into an ostree repo was added)
        with open(args.targets_to_publish_file, 'w') as f:
            json.dump(targets_json, f, indent=2)

        # Update new Targets in unsigned/targets.json before signing it and sending to the OTA server
        with open(args.targets_file, 'r') as f:
            all_targets = json.load(f)
            for target in targets_to_publish:
                all_targets['targets'][target.name] = target.json
                logging.info('New Target: {}\n{}'.format(target.name,
                                                         json.dumps(target.json, ensure_ascii=True, indent=2)))

        with open(args.targets_file, 'w') as f:
            json.dump(all_targets, f, indent=2)

    except Exception as exc:
        logging.exception('Failed to publish Target Apps to Treehub: {}'.format(exc))
        exit_code = 1

    exit(exit_code)
