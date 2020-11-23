# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import logging

from apps.target_apps_fetcher import TargetAppsFetcher
from apps.target_apps_store import ArchiveTargetAppsStore
from apps.ostree_store import OSTreeTargetAppsStore


class TargetPublisher:
    def __init__(self, factory, token, creds, fetch_root_dir, ostree_repo_dir, archive_store_root_dir=None):
        self._fetch_root_dir = fetch_root_dir
        self._ostree_repo_dir = ostree_repo_dir

        self._apps_fetcher = TargetAppsFetcher(token, self._fetch_root_dir)
        self._app_tree_store = OSTreeTargetAppsStore(self._ostree_repo_dir, create=True,
                                                     factory=factory, creds_arch=creds)
        self._app_archive_store = ArchiveTargetAppsStore(archive_store_root_dir) if archive_store_root_dir else None

    def publish(self, targets):
        self.fetch_targets_apps_and_images(targets)
        logging.info('Caching and Publishing Targets\' Apps...')
        for target, _ in self._apps_fetcher.target_apps.items():
            target_apps_branch, target_apps_hash = self._app_tree_store.store(target, self._apps_fetcher.target_dir(target.name))
            targets[target.name]['custom']['compose-apps-branch'] = target_apps_branch
            targets[target.name]['custom']['compose-apps-hash'] = target_apps_hash
            if self._app_archive_store:
                self._app_archive_store.store(target, self._apps_fetcher.images_dir(target.name))

    def fetch_targets_apps_and_images(self, targets):
        logging.info('Fetching Targets\' Apps...')
        self._apps_fetcher.fetch_apps(targets)
        self._apps_fetcher.fetch_apps_images()
