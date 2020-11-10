#!/usr/bin/python3
#
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import argparse
import logging
import json

from apps.target_publisher import TargetPublisher


def get_args():
    parser = argparse.ArgumentParser('''Publish Targets Apps and their images to OSTree repo''')
    parser.add_argument('-f', '--factory', help='Apps Factory')
    parser.add_argument('-a', '--token', help='Factory API Token, aka OSF Token')
    parser.add_argument('-c', '--cred-arch', help='')
    parser.add_argument('-t', '--targets', help='A file containing Targets apps and images of which to dump/fetch')
    parser.add_argument('-nt', '--targets-created',
                        help='A file containing Targets apps and images of which to dump/fetch')
    parser.add_argument('-d', '--fetch-dir', help='Directory to fetch apps and images to')
    parser.add_argument('-o', '--repo-dir', help='Directory to create an ostree repo in')

    args = parser.parse_args()
    return args


def main(factory, token, creds, target_data_root, ostree_repo_dir, targets):
    publisher = TargetPublisher(factory, token, creds, target_data_root, ostree_repo_dir)
    publisher.publish(targets)
    logging.info('Updated Targets\n{}'.format(json.dumps(targets, ensure_ascii=True, indent=2)))


if __name__ == '__main__':
    exit_code = 0
    try:
        logging.basicConfig(format='%(levelname)s: Apps Fetcher: %(module)s: %(message)s', level=logging.INFO)
        args = get_args()
        with open(args.targets_created) as f:
            targets = json.load(f)

        main(args.factory, args.token, args.cred_arch, args.fetch_dir, args.repo_dir, targets)

        with open(args.targets_created, 'w') as f:
            json.dump(targets, f, indent=2)

        with open(args.targets, 'r') as f:
            all_targets = json.load(f)
            for target_name, target_json in targets.items():
                all_targets['targets'][target_name] = target_json

        with open(args.targets, 'w') as f:
            json.dump(all_targets, f, indent=2)

    except Exception as exc:
        logging.error('Failed to fetch Target apps and images: {}'.format(exc))
        exit_code = 1

    exit(exit_code)
