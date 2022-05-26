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
from apps.docker_registry_client import ThirdPartyRegistry
from apps.target_apps_fetcher import SkopeAppFetcher

logger = logging.getLogger(__name__)


def pull_target_apps(target: FactoryClient.Target, oci_store_path: str, token: str, registry_creds: dict = None):
    if registry_creds:
        ThirdPartyRegistry(registry_creds, client='skopeo').login()
    else:
        logger.info("3rd party Registry credentials are not specified")
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

    parser.add_argument('-a', '--token-file', help="A file containing the token to AuthN/AuthZ"
                                                   " at the Fio's Registry to pull Compose Apps",
                        required=True)

    parser.add_argument('-r', '--registry-creds', help="A path to file containing creds to AuthN/AuthZ"
                                                       " at 3rd party registries", required=False)

    parser.add_argument('-l', '--log-file', help="A file to dump logs to", required=False)

    params = parser.parse_args()
    return params


if __name__ == '__main__':
    log_formatter = logging.Formatter('%(asctime)s %(levelname)s: %(module)s: %(message)s')
    stream_hdl = logging.StreamHandler(sys.stdout)
    stream_hdl.setFormatter(log_formatter)

    logging.root.addHandler(stream_hdl)
    logging.root.setLevel('INFO')

    try:
        params = get_args()

        if params.log_file:
            file_hdl = logging.FileHandler(params.log_file)
            file_hdl.setFormatter(log_formatter)
            logging.root.addHandler(file_hdl)

        logger.info(f'Apps Preloading starting; Target json path: {params.target_json_file},'
                    f' shortlist: {params.app_shortlist}, destination OCI store: {params.oci_store_path}')

        with open(params.target_json_file) as target_json_file:
            target_json = json.load(target_json_file)

        registry_creds = None
        if params.registry_creds:
            with open(params.registry_creds) as f:
                registry_creds = json.load(f)

        target_names = list(target_json.keys())
        if len(target_names) == 0:
            logger.error(f'None of Targets are found in the specified target file: {params.target_json_file}')
            sys.exit(os.EX_USAGE)

        if len(target_json.keys()) > 1:
            logger.error(f'More than one Target is found in the specified target file: {params.target_json_file}')
            sys.exit(os.EX_USAGE)

        target_name = target_names[0]
        target = FactoryClient.Target(target_name, target_json[target_name], params.app_shortlist)

        with open(params.token_file) as f:
            token = f.read().strip()

        pull_target_apps(target, params.oci_store_path, token, registry_creds)
        logger.info(f'Apps Preloading succeeded; Target {target.name}, shortlist {target.shortlist}')
    except Exception as exc:
        logger.error('Apps preloading failed: {}\n{}'.format(exc, traceback.format_exc()))
        sys.exit(os.EX_SOFTWARE)
