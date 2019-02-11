#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params PLATFORM

for b in ${FLAKY_TESTS//\\n/ } ; do
	status "Removing flaky test: $b"
	rm -rf $b
done

extra_args=""
if [ -n "$PYOCD_BOARD_NAME" ] ; then
	status "Run is configured for bare-metal testing"

	if [ -z $SUDO_USER ] ; then
		status "Running script with: sudo $0 $*"
		exec sudo -E $0 $*
	fi

	status "Installing dependencies"
	python3 -c "import pyudev; import pyocd" || (echo " *Installing pyudev and pyocd" && (pip3 install pyudev==0.21.0 git+https://github.com/mbedmicro/pyOCD@60e6bf40b713919d9b49ccf4d2753f269d3e6082 | indent))

	status "Probing for a board named: $PYOCD_BOARD_NAME"
	board=$(sudo $(dirname $(readlink -f $0))/pyocd-probe-for $PYOCD_BOARD_NAME)
	board_tty=$(echo $board | cut -d\| -f1)
	board_uid=$(echo $board | cut -d\| -f2)

	status "Probed board tty($board_tty) id($board_uid)"
	extra_args="--device-testing --device-serial $board_tty -e kernel"
fi

. zephyr-env.sh

status "Generating test list"
sanitycheck --platform $PLATFORM --outdir /tmp/outdir -v --ninja --enable-slow --save-tests /archive/test-list

status "Compiling tests"
set -x
sanitycheck  \
	--platform $PLATFORM \
	--inline-logs \
	--outdir /tmp/outdir \
	--enable-slow \
	--verbose \
	--ninja \
	--load-tests /archive/test-list \
|| true

cp ./scripts/sanity_chk/last_sanity.xml /archive/junit.xml
if [ -n "$SAVE_OUTDIR" ] ; then
	status "Saving outdir..."
	cd /tmp && $HERE/archive.py
fi
