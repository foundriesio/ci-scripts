#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
TMPDIR=${TMPDIR-/tmp}

tmpdir=$(mktemp -p $TMPDIR -d test_build.XXXX)
if [ -z "$KEEP" ] ; then
	trap "echo removing tempdir; rm -rf $tmpdir" TERM INT EXIT
else
	echo "temp directory created at: tmpdir"
fi

git clone https://github.com/foundriesio/dm-lwm2m $tmpdir/repo
cd $tmpdir

parent=$(dirname $HERE)
docker run --rm -it -w /repo \
	--entrypoint="" -u root \
	-v $PWD:/archive \
	-v $PWD/repo:/repo \
	-v $parent:$parent \
	-e SAVE_OUTDIR=1 \
	-e PLATFORM=nrf52840_pca10056 \
	zephyrprojectrtos/zephyr-build $HERE/fota-compile.sh
