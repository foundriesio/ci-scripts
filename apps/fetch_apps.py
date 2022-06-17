#!/usr/bin/python3
#
# Copyright (c) 2022 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import argparse
import logging
import traceback
import os
import sys

from factory_client import FactoryClient
from apps.target_apps_fetcher import SkopeAppFetcher

logger = logging.getLogger(__name__)


def fetch_target_apps(target_name: str, factory: str, token: str, dst_dir: str, shortlist: str = None):
    factory_client = FactoryClient(factory, token)
    target = factory_client.get_target(target_name)
    apps_fetcher = SkopeAppFetcher(token, dst_dir, create_target_dir=False)
    apps_fetcher.fetch_target(target, shortlist=shortlist, force=True)


def get_params():
    parser = argparse.ArgumentParser('Fetch Target Apps and their images from Registries to a local file system')
    parser.add_argument('-t', '--target-name', help='Name of Target Apps of which to fetch', required=True)
    parser.add_argument('-f', '--factory', help='Apps Factory', required=True)
    parser.add_argument('-a', '--token-file', help='A file containing Factory API Token, aka OSF Token', required=True)
    parser.add_argument('-d', '--dst-dir', help='Directory to store apps and images in', required=True)
    parser.add_argument('-s', '--shortlist', help='A coma separated list of Target Apps to fetch', default=None)

    return parser.parse_args()


def main():
    exit_code = os.EX_OK
    try:
        params = get_params()

        logger.info(f'Starting fetching Apps; target: {params.target_name}, shortlist: {params.shortlist},'
                    f' destination: {params.dst_dir}')

        with open(params.token_file) as f:
            token = f.read().strip()
        fetch_target_apps(params.target_name, params.factory, token, params.dst_dir, params.shortlist)

        logger.info(f'Apps fetching succeeded; {params.target_name}, shortlist: {params.shortlist},'
                    f' destination: {params.dst_dir}')
    except Exception as exc:
        logger.error('Failed to fetch Target Apps: {}\n{}'.format(exc, traceback.format_exc()))
        exit_code = os.EX_SOFTWARE
    return exit_code


if __name__ == '__main__':
    log_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(module)s: %(message)s')
    stream_hdl = logging.StreamHandler(sys.stdout)
    stream_hdl.setFormatter(log_formatter)
    logging.root.addHandler(stream_hdl)
    logging.root.setLevel('INFO')

    sys.exit(main())
