#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params PLATFORM

for b in ${FLAKY_TESTS//\\n/ } ; do
	status "Removing flaky test: $b"
	rm -rf $b
done

run pip3 install -U west

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
	--load-tests /archive/test-list \
|| true

cp ./scripts/sanity_chk/last_sanity.xml /archive/junit.xml
if [ -n "$SAVE_OUTDIR" ] ; then
	status "Saving outdir..."
	cd /tmp && $HERE/archive.py
fi
