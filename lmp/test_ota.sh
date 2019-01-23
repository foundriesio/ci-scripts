#!/bin/bash -eu

HERE=$(dirname $(readlink -f $0))
TMPDIR=${TMPDIR-/tmp}

tmpdir=$(mktemp -p $TMPDIR -d test_build.XXXX)
trap "echo removing tempdir; rm -rf $tmpdir" TERM INT EXIT

cd $tmpdir

parent=$(dirname $HERE)
docker run --rm -it -w $PWD \
	-v $PWD:/archive \
	-v $PWD:$PWD \
	-v $parent:$parent \
	-e PYTHONPATH=$HERE:$parent \
	hub.foundries.io/ota-runner $HERE/test_ota.py
