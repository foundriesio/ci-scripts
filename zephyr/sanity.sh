#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params PLATFORM

for b in ${FLAKY_TESTS//\\n/ } ; do
	status "Removing flaky test: $b"
	rm -rf $b
done

status "Running sanitycheck"
. zephyr-env.sh
set -x
sanitycheck  \
	--platform $PLATFORM \
	--inline-logs \
	--outdir /tmp/outdir \
	--enable-slow \
	--verbose \
	--ninja \
|| true

cp ./scripts/sanity_chk/last_sanity.xml /archive/junit.xml

