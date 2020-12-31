#!/usr/bin/python3
#
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import argparse
import logging
import json

from factory_client import FactoryClient
from apps.target_publisher import TargetPublisher
from apps.ostree_store import ArchOSTreeTargetAppsStore


def get_args():
    parser = argparse.ArgumentParser('''Fetch Targets Apps and their images''')
    parser.add_argument('-f', '--factory', help='Apps Factory')
    parser.add_argument('-t', '--targets', help='Comma separated list of Targets to dump/fetch')
    parser.add_argument('-a', '--token', help='Factory API Token, aka OSF Token')
    parser.add_argument('-c', '--cred-arch', help='Credentials archive used for auth at Treehub')
    parser.add_argument('-d', '--fetch-dir', help='Directory to fetch/preload/output apps and images')
    parser.add_argument('-s', '--treehub-repo-dir', help='Directory to create a repo to sync with Treehub')
    parser.add_argument('-o', '--repo-dir', help='Directory to create an ostree repo with Targets\' Apps data')
    parser.add_argument('-r', '--ostree-repo-archive-dir', help='OSTree repo archive dir')

    args = parser.parse_args()
    return args


if __name__ == '__main__':
    exit_code = 0
    try:
        logging.basicConfig(format='%(asctime)s %(levelname)s: Apps Fetcher: %(module)s: %(message)s', level=logging.INFO)
        args = get_args()

        target_names = args.targets.split(',')
        factory_client = FactoryClient(args.factory, args.token)

        targets = factory_client.get_targets(target_names)
        app_store = ArchOSTreeTargetAppsStore(args.factory, args.ostree_repo_archive_dir, args.repo_dir)

        publisher = TargetPublisher(args.factory, args.token, args.cred_arch, targets, app_store,
                                    args.fetch_dir, args.treehub_repo_dir)

        publisher.fetch_targets()
        publisher.publish_targets()
        app_store.store_archive()

        for target in targets:
            logging.info('New Target: {}\n{}'.format(target.name,
                                                     json.dumps(target.json, ensure_ascii=True, indent=2)))

    except Exception as exc:
        logging.error('Failed to fetch Target apps and images: {}'.format(exc))
        exit_code = 1

    exit(exit_code)
