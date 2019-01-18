#!/bin/bash -eu

HERE=$(dirname $(readlink -f $0))
TMPDIR=${TMPDIR-/tmp}

tmpdir=$(mktemp -p $TMPDIR -d test_build.XXXX)
trap "echo removing tempdir; sudo rm -rf $tmpdir" TERM INT EXIT

git clone https://github.com/foundriesio/containers-manifest $tmpdir
cd $tmpdir

parent=$(dirname $HERE)
docker run --rm --privileged -it -w $PWD \
	-v $PWD:/archive \
	-v $PWD:$PWD \
	-v $parent:$parent \
	-e GIT_SHA=unit_test \
	-e PRODUCT=gateway \
	-e DRYRUN=1 \
	docker:dind $HERE/rc-tag.sh

echo "Junit Results"
cat $tmpdir/junit.xml
