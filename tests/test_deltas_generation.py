#!/usr/bin/python3

# Example: PYTHONPATH=./ ./tests/test_deltas_generation.py --deltas <deltas-file> --repo <ostree-repo>
# <deltas-file> - a file containing json with ostree commit hashes to create delta:
# [
# 	{
# 		"to": [
# 			"210da9e7a5330473b12a9a2ff9e08fccd8f6f14453e13e0c2c7a5bb7e0f11d05",
# 			"https://api.foundries.io/projects/<factory>/lmp/builds/2051/runs/intel-corei7-64/other/intel-corei7-64-ostree_repo.tar.bz2"
# 			],
# 		"froms": [
# 			[
# 				"ed7ec4eb077f1365ff5b800fa89bc5ec93cba88ceda96d6f87970932ff0bf4b5",
# 				"https://api.foundries.io/projects/<factory>/lmp/builds/2050/runs/intel-corei7-64/other/intel-corei7-64-ostree_repo.tar.bz2"
# 			]
# 		]
# 	}
# ]
#
# <ostree-repo> - a repo that contains all commits referenced in <deltas-file>

import argparse
import json

from typing import List

from lmp.static_deltas import Delta, generate_deltas
from helpers import Progress


def get_args():
    parser = argparse.ArgumentParser('''Generate static deltas''')
    parser.add_argument("-f", "--deltas", help="File with ostree hashes to generate delta for")
    parser.add_argument("-t", "--repo", help="Path to an ostree repo that contains commits"
                                             " to generate delta for")
    return parser.parse_args()


if __name__ == "__main__":
    args = get_args()
    deltas: List[Delta] = []
    with open(args.deltas) as f:
        deltas_json = json.load(f)
        for dj in deltas_json:
            deltas.append(Delta(**dj))

    work = 0
    for d in deltas:
        work += len(d.froms)

    prog = Progress(work)
    generate_deltas(prog, deltas, args.repo)
