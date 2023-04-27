#!/usr/bin/python3
#
# Copyright (c) 2022 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import sys
import os
import logging
import traceback
import argparse
import requests

from helpers import fio_dnsbase

logger = logging.getLogger(__name__)


def get_params():
    parser = argparse.ArgumentParser('Fetch TUF root role metadata')
    parser.add_argument('-f', '--factory', help='Factory name', required=True)
    parser.add_argument('-a', '--token-file', help='A file containing Factory API Token, aka OSF Token', required=True)
    parser.add_argument('-d', '--dst-dir', help='Directory to download metadata to', required=True)
    parser.add_argument('-l', '--log-file', help="A file to dump logs to", required=False)

    return parser.parse_args()


def fetch_all_root_meta(factory: str, token: str, dst: str, prod: bool = False):
    base = fio_dnsbase()
    api_base_url = f'https://api.{base}/ota/repo/{factory}/api/v1/user_repo/'
    ver = 1
    while True:
        meta_file = f"{ver}.root.json"
        logger.info(f"Fetching {meta_file}")
        response = requests.get(os.path.join(api_base_url, meta_file),
                                params={'production': 1} if prod else None, headers={'osf-token': token})
        if response.status_code == 404:
            break

        if not response.ok:
            raise requests.exceptions.HTTPError('Failed to get root meta {}: HTTP_{}\n{}'.
                                                format(meta_file, response.status_code, response.text))

        with open(os.path.join(dst, meta_file), "wb") as f:
            f.write(response.content)
        ver += 1


if __name__ == '__main__':
    exit_code = os.EX_OK

    logging.basicConfig(format='%(asctime)s %(levelname)s: %(module)s: %(message)s', level=logging.INFO)

    try:
        params = get_params()
        if params.log_file:
            file_hdl = logging.FileHandler(params.log_file)
            file_hdl.setFormatter(logging.getLogger().handlers[0].formatter)
            logging.getLogger().addHandler(file_hdl)

        logger.info(f'Starting fetching TUF root role metadata; factory: {params.factory}, dst-dir: {params.dst_dir}')

        with open(params.token_file) as f:
            token = f.read().strip()

        for meta_type in [('ci', False), ('prod', True)]:
            dst = os.path.join(params.dst_dir, meta_type[0])
            logger.info(f'Fetching {meta_type[0]} root metadata to {dst}')
            os.makedirs(dst, exist_ok=True)
            fetch_all_root_meta(params.factory, token, dst, meta_type[1])

        logger.info(f'TUF root role metadata has been successfully downloaded; factory: {params.factory},'
                    f' dst-dir: {params.dst_dir}')
    except Exception as exc:
        logger.error('Failed to fetch TUF root role metadata: {}\n{}'.format(exc, traceback.format_exc()))
        exit_code = os.EX_SOFTWARE

    sys.exit(exit_code)
