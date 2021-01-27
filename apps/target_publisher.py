# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import logging
import subprocess

from apps.target_apps_fetcher import TargetAppsFetcher
from apps.ostree_store import OSTreeRepo


logger = logging.getLogger("Target Publisher")


class TargetPublisher:
    def __init__(self, factory, token, creds, targets, arch_ostree_store, fetch_root_dir, treehub_repo_dir):

        self._creds = creds
        self._arch_ostree_store = arch_ostree_store
        self._fetcher = TargetAppsFetcher(token, fetch_root_dir, factory=factory)
        self._treehub_repo = OSTreeRepo(treehub_repo_dir, create=True)
        self._targets = targets
        self._fetched_targets = []

    def fetch_targets(self):
        logging.info('Fetching Targets\' Apps ...')
        for target in self._targets:
            # make use of the existing apps' images stored in the ostree repo to minimize downloads
            # from docker registries, both the foundries' and hub.docker.io or any other
            if self._arch_ostree_store.exist_branch(target):
                self._arch_ostree_store.checkout(target, self._fetcher.target_dir(target.name))

            self._fetcher.fetch_target(target, force=True)
            target.apps_uri = self._arch_ostree_store.store(target, self._fetcher.target_dir(target.name))
            self._fetched_targets.append(target)

    def publish_targets(self):
        logging.info('Publishing Targets\' Apps ...')
        for target in self._fetched_targets:
            self._treehub_repo.pull_local(self._arch_ostree_store.dir, self._arch_ostree_store.branch(target))
            logger.info('Pushing Compose Apps to Treehub, ref: {}, uri: {} ...'
                        .format(self._arch_ostree_store.branch(target), target.apps_uri))
            subprocess.check_call(['garage-push', '--repo', self._treehub_repo.dir,
                                   '--credentials', self._creds, '--ref', target.apps_commit_hash, '--jobs', '60'],
                                  timeout=12000)
