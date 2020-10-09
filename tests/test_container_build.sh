#!/bin/sh -eu
# Copyright (c) 2019 Foundries.io, SPDX-License-Identifier: Apache-2.0

HERE=$(dirname $(readlink -f $0))
TMPDIR=${TMPDIR-/var/tmp}

tmpdir=$(mktemp -p $TMPDIR -d test_build.XXXX)
trap "echo removing tempdir; rm -rf $tmpdir" TERM INT EXIT

git clone https://github.com/foundriesio/gateway-containers $tmpdir
cd $tmpdir

parent=$(dirname $HERE)
docker run --rm --privileged -it -w $PWD \
	-v $PWD:/archive \
	-v $PWD:$PWD \
	-v $parent:$parent \
	-e FACTORY=test-value \
	-e IMAGES=mosquitto \
	-e GIT_SHA=unit_test \
	docker:dind "${parent}/apps/build.sh"

echo "Junit Results"
cat $tmpdir/junit.xml
