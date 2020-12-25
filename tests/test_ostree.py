# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import unittest
import tempfile
import os

from apps.ostree_store import OSTreeRepo, OSTreeTargetAppsStore
from factory_client import FactoryClient


class OSTreeTest(unittest.TestCase):
    def setUp(self):
        self._repo_dir_tmp = tempfile.TemporaryDirectory('repo')
        self._repo_dir = self._repo_dir_tmp.name
        self._factory = 'test_factory'
        self._branch = 'master'
        self._arch = 'amd64'

        self._ostree_repo = OSTreeRepo(self._repo_dir, create=True)

    def tearDown(self) -> None:
        self._repo_dir_tmp.cleanup()

    def test_create_destroy(self):
        self.assertTrue(self._ostree_repo.initialized())

    def test_create_destroy_instance(self):
        self.assertTrue(self._ostree_repo.initialized())
        read_ostree_repo = OSTreeRepo(self._repo_dir)
        self.assertTrue(read_ostree_repo.initialized())

    def test_create_destroy_instance_negative(self):
        with tempfile.TemporaryDirectory() as tree_dir:
            with self.assertRaises(Exception) as ctx:
                OSTreeRepo(tree_dir)
            self.assertNotEqual(str(ctx.exception).find('Failed to create OSTree repo'), -1)

    def test_commit(self):
        with tempfile.TemporaryDirectory() as tree_dir:
            test_file_name = 'test_file.txt'
            test_file_content = 'some data'
            with open(os.path.join(tree_dir, test_file_name), 'w') as test_file:
                test_file.write(test_file_content)

            branch = 'org.foundries.io/{}/{}/{}'.format(self._factory, self._branch, self._arch)
            hash = self._ostree_repo.commit(tree_dir, branch)
            self.assertEqual(branch, self._ostree_repo.refs())
            self.assertEqual(hash, self._ostree_repo.rev_parse(branch))
            self.assertEqual(test_file_content, self._ostree_repo.cat(hash, test_file_name))
            self.assertEqual(self._ostree_repo.size_in_kbs(), 92)


class OSTreeTargetAppsStoreTest(unittest.TestCase):
    DefaultTarget = {'custom': {
        'arch': 'x86_64',
        'tags': ['devel'],
        'compose-apps-uri': 'sd'
    }}

    def setUp(self):
        self._repo_dir_tmp = tempfile.TemporaryDirectory('repo')
        self._repo_dir = self._repo_dir_tmp.name
        self._app_tree = OSTreeRepo(self._repo_dir, create=True)
        self._app_tree_store = OSTreeTargetAppsStore(self._repo_dir, factory='factory-01')
        self._target = FactoryClient.Target('target-01', OSTreeTargetAppsStoreTest.DefaultTarget)

    def tearDown(self):
        self._repo_dir_tmp.cleanup()

    def test_create_destroy(self):
        self.assertTrue(self._app_tree_store.initialized())

    def test_store(self):
        with tempfile.TemporaryDirectory() as tree_dir:
            test_file_name = 'test_file.txt'
            test_file_content = 'some data'

            with open(os.path.join(tree_dir, test_file_name), 'w') as test_file:
                test_file.write(test_file_content)

            self._target.apps_uri = self._app_tree_store.store(self._target, tree_dir, push_to_treehub=False)

        self.assertTrue(self._app_tree_store.exist(self._target))

    def test_exist_negative_01(self):
        self.assertFalse(self._app_tree_store.exist(self._target))

    def test_exist_negative_02(self):
        with tempfile.TemporaryDirectory() as tree_dir:
            app_tree_store = OSTreeTargetAppsStore(tree_dir)
            self.assertFalse(app_tree_store.initialized())
            self.assertFalse(self._app_tree_store.exist(self._target))
