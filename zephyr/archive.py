#!/usr/bin/python3

# Find all the zephyr build artifacts required for sanitycheck to be able
# to run on another system and tgz them up.

import os
import tarfile

ARCHIVE_FILES = (
    'build.ninja',
    'CMakeCache.txt',
    '.config',
    'zephyr.hex',
    'generated_dts_board.conf',
    'rules.ninja',
)


def scantree(path):
    for entry in os.scandir(path):
        if entry.is_dir(follow_symlinks=False):
            yield from scantree(entry.path)
        else:
            if entry.name in ARCHIVE_FILES:
                yield entry


def main():
    with tarfile.open('/archive/outdir.tgz', 'w:gz') as tgz:
        for x in scantree('./outdir'):
            tgz.add(x.path)


if __name__ == '__main__':
    main()
