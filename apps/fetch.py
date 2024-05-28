#!/usr/bin/python3
#
# Copyright (c) 2021 Foundries.io
# SPDX-License-Identifier: BSD-3-Clause

import argparse
import json
import logging
import traceback
import os
import sys

from apps.target_apps_fetcher import SkopeAppFetcher
from factory_client import FactoryClient
from helpers import cmd


def fetch_target_apps(targets: dict, apps_shortlist: set[str], token: str, dst_dir: str) -> dict[str, set[str]]:
    apps_fetcher = SkopeAppFetcher(token, dst_dir)
    fetched_target_apps: dict[str, set[str]] = {}
    for target_name, target_json in targets.items():
        target = FactoryClient.Target(target_name, target_json)
        target_apps = set(app for app, _ in target.apps())
        target_app_shortlist: set[str] = None
        excluded_apps: set[str] = None
        if apps_shortlist:
            target_app_shortlist = target_apps.intersection(apps_shortlist)
            excluded_apps = apps_shortlist.difference(target_app_shortlist)

        if apps_shortlist and not target_app_shortlist:
            raise Exception(f'No apps found to fetch; target: {target_name};'
                            f' target apps: {",".join(target_apps)};'
                            f' shortlist: {",".join(apps_shortlist)}')
        if excluded_apps and len(excluded_apps) > 0:
            logging.info(f'"{",".join(excluded_apps)}" are excluded from the final shortlist '
                         f'because they are not among target apps: {",".join(target_apps)}')
        logging.info(f'"{",".join(target_app_shortlist if target_app_shortlist else target_apps)}"'
                     f' will be pulled for {target_name}')
        apps_fetcher.fetch_target(target, target_app_shortlist, force=True)
        fetched_target_apps[target_name] = target_app_shortlist

    return fetched_target_apps


def tar_fetched_apps(src_dir: str, out_file: str):
    os.makedirs(os.path.dirname(out_file), exist_ok=True)
    cmd('tar', '-cf', out_file, '-C', src_dir, '.')


def get_args():
    parser = argparse.ArgumentParser('Pull Targets Apps and their images from Registries and '
                                     'store them on a file system')
    parser.add_argument('-f', '--factory', help='Apps Factory', required=True)
    parser.add_argument('-t', '--targets-file',
                        help='A json with Targets to dump/fetch apps for', required=True)
    parser.add_argument('-a', '--token-file',
                        help='File where the Factory API Token is stored', required=True)
    parser.add_argument('-d', '--fetch-dir',
                        help='Directory to fetch apps and images to', required=False)
    parser.add_argument('-s', '--apps-shortlist',
                        help='Comma separated list of Target Apps to fetch', default=None)
    parser.add_argument('-o', '--dst-dir',
                        help='Directory to output the tarred apps data to', required=True)
    parser.add_argument('-tt', '--tuf-targets',
                        help='TUF targets to be updated with URI to fetched app archive')
    parser.add_argument('-dd', '--disable',
                        help='TUF targets to be updated with URI to fetched app archive',
                        default=False, action='store_true')

    args = parser.parse_args()
    return args


def main(args: argparse.Namespace):
    exit_code = os.EX_OK
    try:
        with open(args.token_file) as f:
            token = f.read()
        with open(args.targets_file) as f:
            targets = json.load(f)

        if args.disable:
            logging.info("Disabling apps for offline update...")
            for target, target_json in targets.items():
                target_json["custom"]["fetched-apps"] = {
                    "uri": None
                }
        else:
            shortlist = set([x.strip() for x in args.apps_shortlist.split(',') if x]) \
                if args.apps_shortlist else None

            fetched_target_apps = fetch_target_apps(targets, shortlist, token, args.fetch_dir)
            for target, target_json in targets.items():
                out_file = os.path.join(args.dst_dir, f"{target}.apps.tar")
                logging.info(f"Tarring fetched apps of {target} to {out_file}...")
                tar_fetched_apps(os.path.join(args.fetch_dir, target), out_file)
                target_json["custom"]["fetched-apps"] = {
                    "uri": os.path.join(os.environ["H_RUN_URL"], f"{target}.apps.tar"),
                }
                if fetched_target_apps[target] and len(fetched_target_apps[target]) > 0:
                    target_json["custom"]["fetched-apps"]["shortlist"] = \
                                                                ",".join(fetched_target_apps[target])

        with open(args.targets_file, "w") as f:
            json.dump(targets, f)

        if args.tuf_targets:
            with open(args.tuf_targets, "r") as f:
                tuf_targets = json.load(f)

            tuf_targets["targets"].update(targets)

            with open(args.tuf_targets, "w") as f:
                json.dump(tuf_targets, f)

    except Exception as exc:
        logging.error('Failed to pull Target apps and images: {}\n{}'.format(exc, traceback.format_exc()))
        exit_code = os.EX_SOFTWARE
    return exit_code


if __name__ == '__main__':
    logging.basicConfig(format='%(asctime)s %(levelname)s: Apps Fetcher: %(module)s: %(message)s', level=logging.INFO)
    args = get_args()
    sys.exit(main(args))

