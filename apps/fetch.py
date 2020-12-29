#!/usr/bin/python3
#
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import argparse
import logging

from factory_client import FactoryClient
from apps.target_apps_fetcher import TargetAppsFetcher


def get_args():
    parser = argparse.ArgumentParser('''Fetch Targets Apps and their images''')
    parser.add_argument('-f', '--factory', help='Apps Factory')
    parser.add_argument('-t', '--target', help='A name of Target to dump/fetch')
    parser.add_argument('-a', '--token', help='Factory API Token, aka OSF Token')
    parser.add_argument('-d', '--preload-dir', help='Directory to fetch/preload/output apps and images')
    parser.add_argument('-o', '--out-images-root-dir', help='Directory to output archived images')

    args = parser.parse_args()
    return args


if __name__ == '__main__':
    exit_code = 0
    try:
        logging.basicConfig(format='%(levelname)s: Apps Fetcher: %(module)s: %(message)s', level=logging.INFO)
        args = get_args()

        factory_client = FactoryClient(args.factory, args.token)
        target = factory_client.get_target(args.target)

        TargetAppsFetcher(args.token, args.preload_dir).fetch_target(target, force=True)

    except Exception as exc:
        logging.error('Failed to fetch Target apps and images: {}'.format(exc))
        exit_code = 1

    exit(exit_code)
