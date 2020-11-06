# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import json
import unittest

from contextlib import contextmanager
from tempfile import NamedTemporaryFile

from apps.target_manager import create_target as update_targets

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
                'arch': 'aarch64',
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
                'arch': 'x86_64',
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
                'arch': 'aarch64',
            },
        },
        'imx8mm-11': {
            'hashes': {'sha256': 'YDFHK'},
            'custom': {
                'name': 'imx8mm-lmp',
                'targetFormat': 'OSTREE',
                'tags': ['devel'],
                'version': '11',
                'hardwareIds': ['imx8mm'],
                'arch': 'aarch64',
            },
        },
        'imx8mm-12': {
            'hashes': {'sha256': 'TFTRET'},
            'custom': {
                'name': 'imx8mm-lmp',
                'targetFormat': 'OSTREE',
                'tags': ['devel-feature'],
                'version': '12',
                'hardwareIds': ['imx8mm'],
                'arch': 'aarch64',
            },
        },
    }
}
TARGETS_MACHINES = ['rpi3-cm', 'minnow', 'imx8mm']
ONE_TO_MANY_JSON = ONE_TO_ONE_JSON  # That has what we need for a test

# Default factories have no tags configured
NO_TAGS_JSON = {
    'targets': {
        'rpi3-cm-12': {
            'hashes': {'sha256': 'DEADBEEF'},
            'custom': {
                'name': 'raspberrypi-cm3-lmp',
                'targetFormat': 'OSTREE',
                'version': '12',
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


def create_target(tag, version, targets_file, apps, machines=None, platforms=None):
    if machines is None:
        machines = TARGETS_MACHINES
    update_targets(targets_file, apps, tag, 'some-sha', machines, platforms, version)
    with open(targets_file) as f:
        return json.load(f)


class TestTagging(unittest.TestCase):

    def test_one_to_one(self):
        """Make sure the most basic one-to-one tagging method works."""

        with temp_json_file(ONE_TO_ONE_JSON) as filename:
            create_target('devel', '13', filename, {'app1': {'uri': ''}})
            with open(filename) as f:
                data = json.load(f)
                target = data['targets']['raspberrypi-cm3-lmp-13']
                # we should get the hash of the previous "devel" build
                self.assertEqual('DEADBEEF', target['hashes']['sha256'])
                self.assertEqual(
                    ['app1'], list(target['custom']['docker_compose_apps'].keys()))

                target = data['targets']['minnow-lmp-13']
                # we should get the hash of the previous "devel" build
                self.assertEqual('ABCD', target['hashes']['sha256'])
                self.assertEqual(
                    ['app1'], list(target['custom']['docker_compose_apps'].keys()))

        with temp_json_file(ONE_TO_ONE_JSON) as filename:
            create_target('postmerge', '13', filename, {'app1': {'uri': ''}})
            with open(filename) as f:
                data = json.load(f)
                target = data['targets']['raspberrypi-cm3-lmp-13']
                # we should get the hash of the previous "postmerge" build
                self.assertEqual('G00DBEEF', target['hashes']['sha256'])
                self.assertEqual(
                    ['app1'], list(target['custom']['docker_compose_apps'].keys()))

    def test_one_to_many(self):
        """Check that a single container build can create multiple Targets."""

        with temp_json_file(ONE_TO_MANY_JSON) as filename:
            create_target('devel,postmerge', '13', filename, {'A': {'uri': ''}})
            with open(filename) as f:
                data = json.load(f)

                # This should produce two new targets for "devel":
                target = data['targets']['raspberrypi-cm3-lmp-13-devel']
                self.assertEqual('DEADBEEF', target['hashes']['sha256'])
                self.assertEqual(
                    ['A'], list(target['custom']['docker_compose_apps'].keys()))

                target = data['targets']['minnow-lmp-13-devel']
                self.assertEqual('ABCD', target['hashes']['sha256'])
                self.assertEqual(
                    ['A'], list(target['custom']['docker_compose_apps'].keys()))
                self.assertEqual(['devel'], target['custom']['tags'])

                # And one new target for "postmerge"
                target = data['targets']['raspberrypi-cm3-lmp-13-postmerge']
                # we should get the hash of the previous "postmerge" build
                self.assertEqual(['postmerge'], target['custom']['tags'])
                self.assertEqual('G00DBEEF', target['hashes']['sha256'])
                self.assertEqual(
                    ['A'], list(target['custom']['docker_compose_apps'].keys()))

    def test_no_tags(self):
        """Make sure a factory with no tags defined works."""

        with temp_json_file(NO_TAGS_JSON) as filename:
            create_target('', '13', filename, {'app1': {'uri': ''}})
            with open(filename) as f:
                data = json.load(f)
                target = data['targets']['raspberrypi-cm3-lmp-13']
                # we should get the hash of the previous "devel" build
                self.assertEqual('DEADBEEF', target['hashes']['sha256'])
                self.assertEqual(
                    ['app1'], list(target['custom']['docker_compose_apps'].keys()))

    def test_derive_from_platform(self):
        """Assert that a tag like: postmerge-foo:postmerge works.
           In this scenario a container picks its Platform target based on
           a different target than its named.
        """

        with temp_json_file(ONE_TO_ONE_JSON) as filename:
            create_target(
                'postmerge-foo:postmerge', '13', filename, {'app1': {'uri': ''}})
            with open(filename) as f:
                data = json.load(f)
                target = data['targets']['raspberrypi-cm3-lmp-13']
                # we should get the hash of the previous "postmerge" build
                self.assertEqual('G00DBEEF', target['hashes']['sha256'])
                self.assertEqual(
                    ['app1'], list(target['custom']['docker_compose_apps'].keys()))
                self.assertEqual(['postmerge-foo'], target['custom']['tags'])

    def test_machine_removal(self):
        """Make sure that the new Targets do not include Target of the removed machine."""

        with temp_json_file(ONE_TO_ONE_JSON) as filename:
            create_target('devel', '13', filename, {'app1': {'uri': ''}}, machines=['rpi3-cm'])
            with open(filename) as f:
                data = json.load(f)
                # make sure that only one new Target was added
                self.assertEqual(len(data['targets'].items()), len(ONE_TO_ONE_JSON['targets'].items()) + 1)
                # make sure that only target(s) listed in `machines` was/were included
                self.assertEqual(None, data['targets'].get('minnow-lmp-13'))
                target = data['targets']['raspberrypi-cm3-lmp-13']
                # we should get the hash of the previous "devel" build
                self.assertEqual('DEADBEEF', target['hashes']['sha256'])
                self.assertEqual(['app1'], list(target['custom']['docker_compose_apps'].keys()))

        with temp_json_file(ONE_TO_ONE_JSON) as filename:
            create_target('devel', '13', filename, {'app1': {'uri': ''}}, machines=['minnow'])
            with open(filename) as f:
                data = json.load(f)
                # make sure that only one new Target was added
                self.assertEqual(len(data['targets'].items()), len(ONE_TO_ONE_JSON['targets'].items()) + 1)
                # make sure that only target(s) listed in `machines` was/were included
                self.assertEqual(None, data['targets'].get('raspberrypi-cm3-lmp-13'))
                target = data['targets']['minnow-lmp-13']
                # we should get the hash of the previous "devel" build
                self.assertEqual('ABCD', target['hashes']['sha256'])
                self.assertEqual(['app1'], list(target['custom']['docker_compose_apps'].keys()))

        with temp_json_file(ONE_TO_ONE_JSON) as filename:
            create_target('devel', '13', filename, {'app1': {'uri': ''}}, machines=['rpi3-cm', 'minnow'])
            with open(filename) as f:
                data = json.load(f)
                # make sure that only one new Target was added
                self.assertEqual(len(data['targets'].items()), len(ONE_TO_ONE_JSON['targets'].items()) + 2)
                # make sure that only target(s) listed in `machines` was/were included
                self.assertIsNotNone(data['targets'].get('minnow-lmp-13'))
                self.assertIsNotNone(data['targets'].get('raspberrypi-cm3-lmp-13'))

                target = data['targets']['raspberrypi-cm3-lmp-13']
                self.assertEqual('DEADBEEF', target['hashes']['sha256'])
                self.assertEqual(['app1'], list(target['custom']['docker_compose_apps'].keys()))

                target = data['targets']['minnow-lmp-13']
                self.assertEqual('ABCD', target['hashes']['sha256'])
                self.assertEqual(['app1'], list(target['custom']['docker_compose_apps'].keys()))

    def test_outdated_target(self):
        """Make sure that Targets for the outdated parent Targets are not created"""

        with temp_json_file(ONE_TO_ONE_JSON) as filename:
            create_target('devel', '13', filename, {'app1': {'uri': ''}})
            with open(filename) as f:
                data = json.load(f)
                # make sure that just two new Targets were added
                self.assertEqual(len(data['targets'].items()), len(ONE_TO_ONE_JSON['targets'].items()) + 2)
                # make sure that the outdated Target (version 11) was not added
                self.assertEqual(None, data['targets'].get('imx8mm-lmp-13'))

                # check if all expected Target were created
                target = data['targets']['raspberrypi-cm3-lmp-13']
                # we should get the hash of the previous "devel" build
                self.assertEqual('DEADBEEF', target['hashes']['sha256'])
                self.assertEqual(['app1'], list(target['custom']['docker_compose_apps'].keys()))

                target = data['targets']['minnow-lmp-13']
                self.assertEqual('ABCD', target['hashes']['sha256'])
                self.assertEqual(['app1'], list(target['custom']['docker_compose_apps'].keys()))

        with temp_json_file(ONE_TO_ONE_JSON) as filename:
            create_target('devel-feature', '13', filename, {'app1': {'uri': ''}})
            with open(filename) as f:
                data = json.load(f)
                # make sure that just one new Target was created
                self.assertEqual(len(data['targets'].items()), len(ONE_TO_ONE_JSON['targets'].items()) + 1)
                # make sure that the outdated Target (version 11) was not added
                self.assertIsNotNone(data['targets'].get('imx8mm-lmp-13'))

                target = data['targets']['imx8mm-lmp-13']
                # we should get the hash of the previous "devel-feature" build
                self.assertEqual('TFTRET', target['hashes']['sha256'])
                self.assertEqual(['app1'], list(target['custom']['docker_compose_apps'].keys()))

        with temp_json_file(ONE_TO_ONE_JSON) as filename:
            create_target('devel', '13', filename, {'app1': {'uri': ''}}, machines=['minnow', 'imx8mm'])
            with open(filename) as f:
                data = json.load(f)
                self.assertEqual(len(data['targets'].items()), len(ONE_TO_ONE_JSON['targets'].items()) + 1)
                # make sure that the outdated Target (version 11) was not added
                self.assertEqual(None, data['targets'].get('imx8mm-lmp-13'))

                target = data['targets']['minnow-lmp-13']
                self.assertEqual('ABCD', target['hashes']['sha256'])
                self.assertEqual(['app1'], list(target['custom']['docker_compose_apps'].keys()))

        with temp_json_file(ONE_TO_ONE_JSON) as filename:
            create_target('devel-feature', '13', filename, {'app1': {'uri': ''}}, machines=['minnow'])
            with open(filename) as f:
                data = json.load(f)
                # make sure that zero new Targets were created
                self.assertEqual(len(data['targets'].items()), len(ONE_TO_ONE_JSON['targets'].items()) + 0)

    def test_containers_platforms_compatibility(self):
        """ Make sure that at least one of the platforms of the created containers is compatible
            with an architecture of Target being created
        """
        with temp_json_file(ONE_TO_ONE_JSON) as filename:
            create_target('devel', '13', filename, {'app1': {'uri': ''}},
                          machines=['rpi3-cm', 'minnow'], platforms=['amd'])

            with open(filename) as f:
                data = json.load(f)
                self.assertEqual(len(data['targets'].items()), len(ONE_TO_ONE_JSON['targets'].items()) + 1)
                self.assertIsNone(data['targets'].get('raspberrypi-cm3-lmp-13'))
                self.assertIsNotNone(data['targets'].get('minnow-lmp-13'))
                target = data['targets']['minnow-lmp-13']
                self.assertEqual('ABCD', target['hashes']['sha256'])
                self.assertEqual(['app1'], list(target['custom']['docker_compose_apps'].keys()))

        with temp_json_file(ONE_TO_ONE_JSON) as filename:
            create_target('devel', '13', filename, {'app1': {'uri': ''}},
                          machines=['rpi3-cm'], platforms=['amd', 'arm'])

            with open(filename) as f:
                data = json.load(f)
                self.assertEqual(len(data['targets'].items()), len(ONE_TO_ONE_JSON['targets'].items()) + 1)
                self.assertIsNotNone(data['targets'].get('raspberrypi-cm3-lmp-13'))
                self.assertIsNone(data['targets'].get('minnow-lmp-13'))
                target = data['targets']['raspberrypi-cm3-lmp-13']
                self.assertEqual('DEADBEEF', target['hashes']['sha256'])
                self.assertEqual(['app1'], list(target['custom']['docker_compose_apps'].keys()))

        with temp_json_file(ONE_TO_ONE_JSON) as filename:
            create_target('devel', '13', filename, {'app1': {'uri': ''}},
                          machines=['imx8mm', 'minnow'], platforms=['arm'])

            with open(filename) as f:
                data = json.load(f)
                # imx8mm is outdated so Target should not be created for it
                # there is no container platform (arm) for minnow (x86_64)
                self.assertEqual(len(data['targets'].items()), len(ONE_TO_ONE_JSON['targets'].items()) + 0)
                self.assertIsNone(data['targets'].get('imx8mm-lmp-13'))
                self.assertIsNone(data['targets'].get('minnow-lmp-13'))


if __name__ == '__main__':
    unittest.main()
