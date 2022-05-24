#!/usr/bin/python3
#
# Copyright (c) 2022 Foundries.io
# SPDX-License-Identifier: Apache-2.0
#
import argparse
import logging
import json
import sys
import os
import traceback

from factory_client import FactoryClient
from apps.target_apps_fetcher import SkopeAppFetcher


def pull_target_apps(target: FactoryClient.Target, oci_store_path: str, token: str):
    apps_fetcher = SkopeAppFetcher(token, oci_store_path, create_target_dir=False)
    apps_fetcher.fetch_target(target, force=True)


def get_args():
    parser = argparse.ArgumentParser('''Copy Apps and their images from Registries to a local container image store''')
    parser.add_argument('-t', '--target-json-file',
                        help='A path to a file containing Target json Apps of which to preload',
                        required=True)
    parser.add_argument('-s', '--app-shortlist', help='A coma separated list of Target Apps to copy.'
                                                      'If not specified or empty, then all Target Apps are copied',
                        default="")
    parser.add_argument('-d', '--oci-store-path', help="A path to a local OCI image store to copy images to",
                        required=True)

    parser.add_argument('-a', '--token', help="A token to authN/authZ at the Fio's Registry to pull Compose Apps",
                        required=True)

    params = parser.parse_args()
    return params


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(module)s: %(message)s', level=logging.INFO)
    try:
        params = get_args()

        logging.info(f'Preloading Apps; Target json path: {params.target_json_file},'
                     f' shortlist: {params.app_shortlist}, destination OCI store: {params.oci_store_path}')

        with open(params.target_json_file) as target_json_file:
            target_json = json.load(target_json_file)

        target_names = list(target_json.keys())
        if len(target_names) == 0:
            logging.error(f'None of Targets are found in the specified target file: {params.target_json_file}')
            sys.exit(os.EX_USAGE)

        if len(target_json.keys()) > 1:
            logging.error(f'More than one Target is found in the specified target file: {params.target_json_file}')
            sys.exit(os.EX_USAGE)

        target_name = target_names[0]
        target = FactoryClient.Target(target_name, target_json[target_name], params.app_shortlist)

        pull_target_apps(target, params.oci_store_path, params.token)
    except Exception as exc:
        logging.error('Failed to preload Apps: {}\n{}'.format(exc, traceback.format_exc()))
        sys.exit(os.EX_SOFTWARE)