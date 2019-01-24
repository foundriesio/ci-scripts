#!/bin/bash -eu

HERE=$(dirname $(readlink -f $0))
TMPDIR=${TMPDIR-/tmp}

tmpdir=$(mktemp -p $TMPDIR -d test_build.XXXX)
trap "echo removing tempdir; rm -rf $tmpdir" TERM INT EXIT

git clone https://github.com/foundriesio/lmp-manifest $tmpdir
cd $tmpdir
mkdir downloads && mkdir sstate-cache-lmp

parent=$(dirname $HERE)
docker run --rm -it -w $PWD \
	-v $PWD:/archive \
	-v $PWD:$PWD \
	-v $parent:$parent \
	-v $PWD:/var/cache/bitbake \
	-e IMAGE='-h' \
	-e GIT_SHA=master\
	-e MACHINE=raspberrypi3-64 \
	hub.foundries.io/lmp-sdk $HERE/build.sh
