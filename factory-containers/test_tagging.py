import json
import os
import subprocess
import unittest

from contextlib import contextmanager
from tempfile import NamedTemporaryFile

ONE_TO_ONE_JSON = {
    'targets': {
        'rpi3-cm-12': {
            'hashes': {'sha256': 'DEADBEEF'},
            'custom': {
                'name': 'raspberrypi-cm3-lmp',
                'targetFormat': 'OSTREE',
                'tags': ['devel'],
                'version': '12',
                'hardwareIds': ['rpi3-cm'],
            },
        },
        'minnow-12': {
            'hashes': {'sha256': 'ABCD'},
            'custom': {
                'name': 'minnow-lmp',
                'targetFormat': 'OSTREE',
                'tags': ['devel'],
                'version': '12',
                'hardwareIds': ['minnow'],
            },
        },
        'rpi3-cm-10': {
            'hashes': {'sha256': 'G00DBEEF'},
            'custom': {
                'name': 'raspberrypi-cm3-lmp',
                'targetFormat': 'OSTREE',
                'tags': ['postmerge'],
                'version': '10',
                'hardwareIds': ['rpi3-cm'],
            },
        },
    }
}


@contextmanager
def temp_json_file(data):
    with NamedTemporaryFile(mode='w') as f:
        json.dump(data, f)
        f.flush()
        yield f.name


def create_target(tag, version, targets_file, apps):
    args = ['./ota-dockerapp.py', 'create-target', version, targets_file]
    args.extend(apps)
    env = os.environ.copy()
    env['OTA_LITE_TAG'] = tag
    subprocess.check_call(args, env=env, cwd=os.path.dirname(__file__))
    with open(targets_file) as f:
        return json.load(f)


class TestTagging(unittest.TestCase):

    def test_one_to_one(self):
        """Make sure the most basic one-to-one tagging method works."""

        with temp_json_file(ONE_TO_ONE_JSON) as filename:
            create_target('devel', '13', filename, ['app1.dockerapp'])
            with open(filename) as f:
                data = json.load(f)
                target = data['targets']['raspberrypi-cm3-lmp-13']
                # we should get the hash of the previous "devel" build
                self.assertEqual('DEADBEEF', target['hashes']['sha256'])
                self.assertEqual(
                    ['app1'], list(target['custom']['docker_apps'].keys()))

                target = data['targets']['minnow-lmp-13']
                # we should get the hash of the previous "devel" build
                self.assertEqual('ABCD', target['hashes']['sha256'])
                self.assertEqual(
                    ['app1'], list(target['custom']['docker_apps'].keys()))

        with temp_json_file(ONE_TO_ONE_JSON) as filename:
            create_target('postmerge', '13', filename, ['app1.dockerapp'])
            with open(filename) as f:
                data = json.load(f)
                target = data['targets']['raspberrypi-cm3-lmp-13']
                # we should get the hash of the previous "postmerge" build
                self.assertEqual('G00DBEEF', target['hashes']['sha256'])
                self.assertEqual(
                    ['app1'], list(target['custom']['docker_apps'].keys()))


if __name__ == '__main__':
    unittest.main()
