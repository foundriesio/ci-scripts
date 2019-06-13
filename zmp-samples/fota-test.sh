#!/bin/sh -ex

export LOG_DIR=/archive
python3 -m mp_e2e.sanity ZMP_BUILD=$H_BUILD PLATFORM="$PLATFORM" \
	CI_PROJECT=$H_PROJECT \
	CI_RUN=$(basename $H_TRIGGER_URL)
