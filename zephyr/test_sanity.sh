#!/bin/bash -eu

HERE=$(dirname $(readlink -f $0))
TMPDIR=${TMPDIR-/tmp}

tmpdir=$(mktemp -p $TMPDIR -d test_build.XXXX)
if [ -z "$KEEP" ] ; then
	trap "echo removing tempdir; rm -rf $tmpdir" TERM INT EXIT
else
	echo "temp directory created at: tmpdir"
fi

git clone https://github.com/zephyrproject-rtos/zephyr.git $tmpdir
cd $tmpdir

parent=$(dirname $HERE)
docker run --rm -it -w /repo \
	-v $PWD:/archive \
	-v $PWD:/repo \
	-v $parent:$parent \
	-e SAVE_OUTDIR=1 \
	-e GIT_SHA=master \
	-e PLATFORM=nrf52_blenano2 \
	zephyrprojectrtos/zephyr-build $HERE/sanity-compile.sh

echo "= Junit Results"
cat $tmpdir/junit.xml

echo "= outdir.tgz:"
tar -tzf $tmpdir/outdir.tgz
du -sh $tmpdir/outdir.tgz
