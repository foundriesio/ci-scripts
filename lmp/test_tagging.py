import json
import os
import subprocess
import unittest

from contextlib import contextmanager
from tempfile import NamedTemporaryFile

TARGETS_JSON = {
    'targets': {
        'rpi3-cm-12': {
            'hashes': {'sha256': 'DEADBEEF'},
            'custom': {
                'name': 'raspberrypi-cm3-lmp',
                'targetFormat': 'OSTREE',
                'tags': ['devel'],
                'version': '12',
                'hardwareIds': ['rpi3-cm'],
                'docker_apps': {'foo': 'devel-r'},
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
                'docker_apps': {'foo': 'devel-m'},
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
                'docker_apps': {'foo': 'postmerge-r'},
            },
        },
        'rpi3-cm-13': {
            'hashes': {'sha256': 'BADBEEF'},
            'custom': {
                'name': 'raspberrypi-cm3-lmp',
                'targetFormat': 'OSTREE',
                'version': '13',
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


def customize_target(tag, targets_file, target_name):
    args = ['./customize-target', targets_file, target_name]
    env = os.environ.copy()
    env['OTA_LITE_TAG'] = tag
    subprocess.check_call(args, env=env, cwd=os.path.dirname(__file__))
    with open(targets_file) as f:
        return json.load(f)


class TestTagging(unittest.TestCase):

    def test_one_to_one(self):
        """Make sure the most basic one-to-one tagging method works."""

        with temp_json_file(TARGETS_JSON) as filename:
            customize_target('devel', filename, 'rpi3-cm-13')
            with open(filename) as f:
                data = json.load(f)
                target = data['targets']['rpi3-cm-13']
                # we should get the hash of the previous "devel" build
                self.assertEqual('BADBEEF', target['hashes']['sha256'])
                self.assertEqual(['devel'], target['custom']['tags'])
                self.assertEqual(
                    {'foo': 'devel-r'}, target['custom']['docker_apps'])

        with temp_json_file(TARGETS_JSON) as filename:
            customize_target('postmerge', filename, 'rpi3-cm-13')
            with open(filename) as f:
                data = json.load(f)
                target = data['targets']['rpi3-cm-13']
                # we should get the hash of the previous "devel" build
                self.assertEqual('BADBEEF', target['hashes']['sha256'])
                self.assertEqual(['postmerge'], target['custom']['tags'])
                self.assertEqual(
                    {'foo': 'postmerge-r'}, target['custom']['docker_apps'])

    def test_alternate_containers(self):
        """Grab containers from a different tag"""

        with temp_json_file(TARGETS_JSON) as filename:
            customize_target('devel:postmerge', filename, 'rpi3-cm-13')
            with open(filename) as f:
                data = json.load(f)
                target = data['targets']['rpi3-cm-13']
                # we should get the hash of the previous "devel" build
                self.assertEqual('BADBEEF', target['hashes']['sha256'])
                self.assertEqual(['devel'], target['custom']['tags'])
                self.assertEqual(
                    {'foo': 'postmerge-r'}, target['custom']['docker_apps'])

    def test_no_tags(self):
        """Grab the latest containers if no tags are used."""

        with temp_json_file(TARGETS_JSON) as filename:
            customize_target('', filename, 'rpi3-cm-13')
            with open(filename) as f:
                data = json.load(f)
                target = data['targets']['rpi3-cm-13']
                # we should get the hash of the previous "devel" build
                self.assertEqual('BADBEEF', target['hashes']['sha256'])
                self.assertIsNone(target['custom'].get('tags'))
                self.assertEqual(
                    {'foo': 'devel-r'}, target['custom']['docker_apps'])

    def test_multiple_targets(self):
        """A single platform build can produce more than one target."""
        with temp_json_file(TARGETS_JSON) as filename:
            # Dumb - but have one target be "devel" but with containers
            # from "postmerge". Tag another target "postmerge" but with
            # containers from "devel"
            customize_target(
                'devel:postmerge,postmerge:devel', filename, 'rpi3-cm-13')
            with open(filename) as f:
                data = json.load(f)
                target = data['targets']['rpi3-cm-13']
                # we should get the hash of the previous "devel" build
                self.assertEqual('BADBEEF', target['hashes']['sha256'])
                self.assertEqual(['devel'], target['custom']['tags'])
                self.assertEqual(
                    {'foo': 'postmerge-r'}, target['custom']['docker_apps'])

                target = data['targets']['rpi3-cm-13-1']
                # we should get the hash of the previous "devel" build
                self.assertEqual('BADBEEF', target['hashes']['sha256'])
                self.assertEqual(['postmerge'], target['custom']['tags'])
                self.assertEqual(
                    {'foo': 'devel-r'}, target['custom']['docker_apps'])
