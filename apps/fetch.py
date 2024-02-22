#!/usr/bin/python3
#
# Copyright (c) 2021 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import argparse
import logging
import traceback
import os
import sys

from factory_client import FactoryClient
from apps.target_apps_fetcher import SkopeAppFetcher


def get_args():
    parser = argparse.ArgumentParser('Pull Targets Apps and their images from Registries and '
                                     'store them on a file system')
    parser.add_argument('-f', '--factory', help='Apps Factory', required=True)
    parser.add_argument('-t', '--targets', help='Comma separated list of Targets to dump/fetch', required=True)
    parser.add_argument('-a', '--token-file', help='File where the Factory API Token is stored', required=True)
    parser.add_argument('-d', '--dst-dir', help='Directory to store apps and images in', required=True)
    parser.add_argument('-s', '--apps-shortlist', help='A coma separated list of Target Apps to fetch', default=None)

    args = parser.parse_args()
    return args


def main(args: argparse.Namespace):
    exit_code = os.EX_OK
    try:
        target_list = args.targets.split(',')
        with open(args.token_file) as f:
            token = f.read()
        factory_client = FactoryClient(args.factory, token)

        targets = factory_client.get_targets(target_list)
        if len(targets) == 0:
            raise Exception(f"No targets found in the factory; factory: {args.factory}, {target_list}")
        apps_fetcher = SkopeAppFetcher(token, args.dst_dir)
        for target in targets:
            target.shortlist = args.apps_shortlist
            apps_fetcher.fetch_target(target, force=True)

    except Exception as exc:
        logging.error('Failed to pull Target apps and images: {}\n{}'.format(exc, traceback.format_exc()))
        exit_code = os.EX_SOFTWARE
    return exit_code


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(levelname)s: Apps Puller: %(module)s: %(message)s', level=logging.INFO)
    args = get_args()
    sys.exit(main(args))

