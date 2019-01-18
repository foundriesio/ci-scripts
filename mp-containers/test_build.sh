#!/bin/bash -eu

HERE=$(dirname $(readlink -f $0))
TMPDIR=${TMPDIR-/tmp}

tmpdir=$(mktemp -p $TMPDIR -d test_build.XXXX)
trap "echo removing tempdir; rm -rf $tmpdir" TERM INT EXIT

git clone https://github.com/foundriesio/gateway-containers $tmpdir
cd $tmpdir

parent=$(dirname $HERE)
docker run --rm --privileged -it -w $PWD \
	-v $PWD:/archive \
	-v $PWD:$PWD \
	-v $parent:$parent \
	-e IMAGES=mosquitto \
	-e GIT_SHA=unit_test \
	docker:dind $HERE/build.sh

echo "Junit Results"
cat $tmpdir/junit.xml
