# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: BSD-3-Clause

from apps.compose_apps import ComposeApps


import shutil
import unittest
import tempfile
import os
import yaml


class ComposeAppsTest(unittest.TestCase):
    ComposeAppDesc = '''
    services:
      nginx-01:
        image: hub.foundries.io/test_factory/nginx
        ports:
        - ${PORT-9999}:80
        restart: always
      nginx-02:
        image: nginx:1.19.2-alpine
        ports:
        - ${PORT-8888}:80
        restart: always
      python-www:
        image: hub.foundries.io/test_factory/app-07:latest
        ports:
        - 9987:80
        restart: always
        volumes:
        - .:/var/http
    version: '3.2'
    '''

    def setUp(self):
        self.apps_root_dir = tempfile.mkdtemp()
        self.app_name = 'app1'
        os.mkdir(os.path.join(self.apps_root_dir, self.app_name))
        with open(os.path.join(self.apps_root_dir, self.app_name, ComposeApps.App.ComposeFile), 'w') as compose_file:
            yaml_data = yaml.safe_load(self.ComposeAppDesc)
            yaml.dump(yaml_data, compose_file)

    def tearDown(self):
        shutil.rmtree(self.apps_root_dir)

    def test_compose_apps_init(self):
        apps = ComposeApps(self.apps_root_dir)
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps.str, self.app_name)
        self.assertEqual(len(apps), 1)

    def test_compose_apps_app_init(self):
        app = ComposeApps(self.apps_root_dir)[0]
        self.assertEqual(len(app.services()), 3)

    def test_compose_apps_app_images(self):
        app = ComposeApps(self.apps_root_dir)[0]
        expected_images = ['hub.foundries.io/test_factory/nginx',
                           'nginx:1.19.2-alpine',
                           'hub.foundries.io/test_factory/app-07:latest']
        for image in app.images():
            self.assertIn(image, expected_images)

    # def test_compose_apps_app_image_tagging(self):
    #     app = self.apps[0]
    #     tag = '192837465'
    #     app.tag_images(tag, 'hub.foundries.io/test_factory')
    #
    #     expected_images = ['hub.foundries.io/test_factory/nginx:{}'.format(tag),
    #                        'nginx:1.19.2-alpine',
    #                        'hub.foundries.io/test_factory/app-07:{}'.format(tag)]
    #     for image in app.images():
    #         self.assertIn(image, expected_images)


if __name__ == '__main__':
    unittest.main()
