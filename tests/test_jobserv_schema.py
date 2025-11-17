# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: BSD-3-Clause

import os
import sys
import unittest

import requests
import yaml


class JobservSchemaTest(unittest.TestCase):
    def test_schema(self):
        here = os.path.abspath(__file__)
        root = os.path.dirname(os.path.dirname(here))

        paths = ("lmp/jobserv.yml", "factory-containers/jobserv.yml")
        for p in paths:
            with open(os.path.join(root, p)) as f:
                data = yaml.safe_load(f)
                r = requests.post("https://api.foundries.io/simulator-validate", json=data)
                if r.status_code != 200:
                    try:
                        sys.exit(r.json()['message'])
                    except Exception:
                        sys.exit(r.text)
