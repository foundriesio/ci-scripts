#!/usr/bin/python3
#
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import argparse
import logging
import json
import traceback

from apps.target_apps_fetcher import TargetAppsFetcher
from apps.target_apps_store import ArchiveTargetAppsStore


def get_args():
    parser = argparse.ArgumentParser('''Fetch Targets Apps and their images''')
    parser.add_argument('-f', '--factory', help='Apps Factory')
    parser.add_argument('-t', '--targets', help='A file containing Targets apps and images of which to dump/fetch')
    parser.add_argument('-a', '--token', help='Factory API Token, aka OSF Token')
    parser.add_argument('-d', '--preload-dir', help='Directory to fetch/preload/output apps and images')
    parser.add_argument('-o', '--out-images-root-dir', help='Directory to output archived images')
    parser.add_argument('-s', '--app-shortlist', help='A coma separated list of Target Apps to fetch', default=None)

    args = parser.parse_args()
    if args.app_shortlist:
        args.app_shortlist = args.app_shortlist.split(',')
    return args


if __name__ == '__main__':
    exit_code = 0
    try:
        logging.basicConfig(format='%(levelname)s: Apps Fetcher: %(module)s: %(message)s', level=logging.INFO)
        args = get_args()
        with open(args.targets) as f:
            targets = json.load(f)

        apps_fetcher = TargetAppsFetcher(args.token, args.preload_dir)
        apps_fetcher.fetch_apps(targets, apps_shortlist=args.app_shortlist)
        apps_fetcher.fetch_apps_images()

        store = ArchiveTargetAppsStore(args.out_images_root_dir)
        for target, _ in apps_fetcher.target_apps.items():
            store.store(target, apps_fetcher.target_dir(target.name))
    except Exception as exc:
        # since preloading/fetching of App container images are not really mandatory
        # we return successful exit code and just output an error message along with s stack trace
        logging.error('Failed to fetch Target apps and images: {}\n{}'.format(exc, traceback.format_exc()))
        exit_code = 0

    exit(exit_code)
