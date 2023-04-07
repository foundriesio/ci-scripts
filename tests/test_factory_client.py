import os
import unittest
from unittest.mock import MagicMock, patch

import requests
import requests_mock
from tempfile import TemporaryDirectory

from factory_client import FactoryClient
from helpers import Progress


class TestFactoryClient(unittest.TestCase):
    @patch("subprocess.check_call")
    @patch("helpers.status")
    def test_system_image_fetching(self, check_call, status_print):
        factory = "test-factory"
        api_url = "https://api.f.io"
        client = FactoryClient(factory, "some-token", factory_api_base_url=api_url)
        target = FactoryClient.Target("test-target", {
            "custom": {
                "hardwareIds": [
                    "intel-corei7-64"
                ],
                "image-file": "lmp-factory-image-intel-corei7-64.wic.gz",
                "uri": f"https://ci.foundries.io/projects/{factory}/lmp/builds/1"
            }
        })

        with self.subTest("Get WIC image file successfully"):
            with TemporaryDirectory() as out_dir:
                with requests_mock.Mocker() as m:
                    m.get(f"{api_url}/projects/{factory}/lmp/builds/1/runs/"
                          f"{target['custom']['hardwareIds'][0]}/{target['custom']['image-file']}",
                          text='wic image content')
                    file_path = client.get_target_system_image(target, out_dir, Progress(1))
                    #  check if the gz file exists since we mock the `gunzip` call (check_call)
                    self.assertTrue(os.path.exists(file_path + ".gz"))

        with self.subTest("WIC image is not found"):
            with TemporaryDirectory() as out_dir:
                with requests_mock.Mocker() as m:
                    m.get(f"{api_url}/projects/{factory}/lmp/builds/1/runs/"
                          f"{target['custom']['hardwareIds'][0]}/{target['custom']['image-file']}",
                          text='Not Found', status_code=404)
                    try:
                        file_path = client.get_target_system_image(target, out_dir, Progress(1))
                    except requests.HTTPError as exc:
                        self.assertEqual(404, exc.response.status_code)
                    #  check if the gz file exists since we mock the `gunzip` call (check_call)
                    self.assertFalse(os.path.exists(file_path + ".gz"))


if __name__ == '__main__':
    unittest.main()
