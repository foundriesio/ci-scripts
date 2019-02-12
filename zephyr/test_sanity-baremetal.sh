#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
TMPDIR=${TMPDIR-/tmp}

tmpdir=$(mktemp -p $TMPDIR -d test_build.XXXX)
if [ -z "$KEEP" ] ; then
	trap "echo removing tempdir; sudo rm -rf $tmpdir" TERM INT EXIT
else
	echo "temp directory created at: tmpdir"
fi

parent=$(dirname $HERE)
docker run --rm -it --privileged -w $PWD \
	-v $PWD:/archive \
	-v $parent:$parent \
	-e H_TRIGGER_URL="https://api.foundries.io/projects/zephyr/builds/4834/runs/sanity-compile-nrf52/" \
	-e GIT_URL="https://github.com/foundriesio/zephyr.git" \
	-e GIT_SHA=master \
	-e PLATFORM=nrf52_blenano2 \
	-e PYOCD_BOARD_NAME=RedBearLab-BLE-Nano2 \
	zephyrprojectrtos/zephyr-build $HERE/sanity-device.sh

echo "Junit Results"
cat $tmpdir/junit.xml
