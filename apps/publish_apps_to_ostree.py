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
    parser.add_argument('-t', '--targets-file', help='A file containing all Factory Targets')
    parser.add_argument('-nt', '--targets-to-publish-file',
                        help='A file containing Targets apps and images of which to publish')
    parser.add_argument('-d', '--fetch-dir', help='Directory to fetch apps and images to')
    parser.add_argument('-o', '--repo-dir', help='Directory to create an ostree repo in')
    parser.add_argument('-ar', '--archive-root-dir', help='Directory to output Apps archive to')

    args = parser.parse_args()
    return args


def main(factory, token, creds, fetch_root_dir, ostree_repo_dir, targets, archive_root_dir=None):
    logging.info('Publishing Apps to Treehub...')
    TargetPublisher(factory, token, creds, fetch_root_dir, ostree_repo_dir, archive_root_dir).publish(targets)
    logging.info('Updated Targets\n{}'.format(json.dumps(targets, ensure_ascii=True, indent=2)))


if __name__ == '__main__':
    exit_code = 0
    try:
        logging.basicConfig(format='%(asctime)s %(levelname)s: %(module)s: %(message)s', level=logging.INFO)
        args = get_args()
        with open(args.targets_to_publish_file) as f:
            targets_to_publish = json.load(f)

        main(args.factory, args.token, args.cred_arch, args.fetch_dir, args.repo_dir,
             targets_to_publish, args.archive_root_dir)

        # Update targets-created.json (hash of a commit into an ostree repo was added)
        with open(args.targets_to_publish_file, 'w') as f:
            json.dump(targets_to_publish, f, indent=2)

        # Update new Targets in unsigned/targets.json before signing it and sending to the OTA server
        with open(args.targets_file, 'r') as f:
            all_targets = json.load(f)
            for target_name, target_json in targets_to_publish.items():
                all_targets['targets'][target_name] = target_json

        with open(args.targets_file, 'w') as f:
            json.dump(all_targets, f, indent=2)

    except Exception as exc:
        logging.exception('Failed to publish Target Apps to Treehub: {}'.format(exc))
        exit_code = 1

    exit(exit_code)
