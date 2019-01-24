#!/usr/bin/python3
import os
import unittest

from unittest.mock import patch

import ota_test


class Test(unittest.TestCase):
    def setUp(self):
        super().setUp()
        if os.path.exists('/archive/execute-on-reboot'):
            os.unlink('/archive/execute-on-reboot')
        if os.path.exists('/archive/execute-on-cold-reboot'):
            os.unlink('/archive/execute-on-cold-reboot')

    def test_reboot_script(self):
        ota_test._create_reboot_script(False)
        self.assertTrue(os.path.exists('/archive/execute-on-reboot'))
        ota_test._create_reboot_script(True)
        self.assertTrue(os.path.exists('/archive/execute-on-cold-reboot'))

    @patch('ota_test._test_booted_image')
    def test_cold(self, tbi):
        ota_test.cold_main()
        self.assertTrue(os.path.exists('/archive/execute-on-reboot'))
        with open('/archive/execute-on-reboot') as f:
            print('Reboot script:')
            print(f.read())


if __name__ == '__main__':
    unittest.main()
