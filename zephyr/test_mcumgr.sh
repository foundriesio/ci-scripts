#!/bin/bash -eu

HERE=$(dirname $(readlink -f $0))
TMPDIR=${TMPDIR-/tmp}

tmpdir=$(mktemp -p $TMPDIR -d test_build.XXXX)
trap "echo removing tempdir; rm -rf $tmpdir" TERM INT EXIT

git clone https://github.com/zephyrproject-rtos/zephyr.git $tmpdir
cd $tmpdir

parent=$(dirname $HERE)
docker run --rm -it -w $PWD \
	-v $PWD:/archive \
	-v $PWD:$PWD \
	-v $parent:$parent \
	-e GIT_SHA=master \
	-e PLATFORM=reel_board \
	-e APP=samples/subsys/mgmt/mcumgr/smp_svr/ \
	zephyrprojectrtos/zephyr-build $HERE/sample.sh
