# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import unittest
import tempfile
import os

from apps.ostree_store import OSTreeRepo


class OSTreeTest(unittest.TestCase):
    def setUp(self):
        self._repo_dir_tmp = tempfile.TemporaryDirectory('repo')
        self._repo_dir = self._repo_dir_tmp.name
        self._factory = 'test_factory'
        self._branch = 'master'
        self._arch = 'amd64'

        self._ostree_repo = OSTreeRepo(self._repo_dir)

    def tearDown(self) -> None:
        self._repo_dir_tmp.cleanup()

    def test_create_destroy(self):
        self.assertTrue(self._ostree_repo.initialized())

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

