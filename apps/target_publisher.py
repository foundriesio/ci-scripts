# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import logging

from apps.target_apps_fetcher import TargetAppsFetcher
from apps.ostree_store import OSTreeTargetAppsStore


class TargetPublisher:
    def __init__(self, factory, token, creds, target_data_root, ostree_repo_dir):
        self._data_root = target_data_root
        self._ostree_repo_dir = ostree_repo_dir

        self._apps_fetcher = TargetAppsFetcher(token, self._data_root)
        self._repo = OSTreeTargetAppsStore(factory, self._ostree_repo_dir, creds)

    def publish(self, targets):
        self.fetch_targets_apps_and_images(targets)
        for target, _ in self._apps_fetcher.target_apps.items():
            target_apps_hash = self._repo.store(target, self._apps_fetcher.target_dir(target.name))
            targets[target.name]['custom']['compose-apps-hash'] = target_apps_hash

    def fetch_targets_apps_and_images(self, targets):
        self._apps_fetcher.fetch_apps(targets)
        self._apps_fetcher.fetch_apps_images()
