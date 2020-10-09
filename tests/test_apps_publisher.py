# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

from apps.compose_apps import ComposeApps
from apps.apps_publisher import AppsPublisher

import shutil
import unittest
import tempfile
import os
import yaml


class ComposeAppsPublisherTest(unittest.TestCase):
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
        self.factory = 'test_factory'
        self.publish_tool = 'some-fake-publish-tool'

        os.mkdir(os.path.join(self.apps_root_dir, self.app_name))
        with open(os.path.join(self.apps_root_dir, self.app_name, ComposeApps.App.ComposeFile), 'w') as compose_file:
            yaml_data = yaml.safe_load(self.ComposeAppDesc)
            yaml.dump(yaml_data, compose_file)

        self.apps = ComposeApps(self.apps_root_dir)
        self.publisher = AppsPublisher(self.factory, self.publish_tool)

    def tearDown(self):
        shutil.rmtree(self.apps_root_dir)

    def test_compose_apps_image_tagging(self):
        tag = '192837465'

        self.publisher.tag(self.apps, tag)

        expected_images = ['hub.foundries.io/test_factory/nginx:{}'.format(tag),
                           'nginx:1.19.2-alpine',
                           'hub.foundries.io/test_factory/app-07:{}'.format(tag)]
        for image in self.apps[0].images():
            self.assertIn(image, expected_images)

    # TODO: implement AppsPublisher::publish test, requires emulator/mock of the compose-publisher/compose-ref tool
    # unless we implement it in python
    # def test_compose_apps_publishing(self):


if __name__ == '__main__':
    unittest.main()
