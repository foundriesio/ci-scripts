#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params IMAGE

start_ssh_agent

source setup-environment build

# Parsing first, to stop in case of parsing issues
bitbake -p

# Global and image specific envs
bitbake -e > ${archive}/bitbake_global_env.txt
bitbake -e ${IMAGE} > ${archive}/bitbake_image_env.txt

# Before LmP version 87 (first release with OE-core kirkstone),
# this is need to avoid build failures that can recover in the next steps
if [ "$LMP_VERSION" -lt "87" ]; then
    bitbake --setscene-only ${IMAGE} || true
fi

if [ "$BUILD_SDK" == "1" ] && [ "${DISTRO}" != "lmp-mfgtool" ]; then
    bitbake -D ${BITBAKE_EXTRA_ARGS} ${IMAGE} -c populate_sdk
fi
bitbake -D ${BITBAKE_EXTRA_ARGS} ${IMAGE}

# we need to check that because it is not available before kirkstone
if command -v bitbake-getvar >/dev/null 2>&1; then
    # get buildstats path
    BUILDSTATS_PATH="$(bitbake-getvar --value TMPDIR | tail -n 1)/buildstats"
fi
# check if the buildstats was enabled
if [ -d "$BUILDSTATS_PATH" ]; then
    # get the most recent folder
    BUILDSTATS_PATH="$(ls -td -- $BUILDSTATS_PATH/*/ | head -n 1)"
    # write a summary of the buildstats to the terminal
    BUILDSTATS_SUMMARY="../layers/openembedded-core/scripts/buildstats-summary"
    # we need to check that because it is only available in the kirkstone branch
    if [ -f $BUILDSTATS_SUMMARY ]; then
        # common arguments with bold disabled
        BUILDSTATS_SUMMARY="$BUILDSTATS_SUMMARY --sort duration --highlight 0"
        # log all task
        $BUILDSTATS_SUMMARY $BUILDSTATS_PATH > ${archive}/bitbake_buildstats.log
        # for console hide tasks < Seconds
        BUILDSTATS_SUMMARY="$BUILDSTATS_SUMMARY --shortest 60"
        run $BUILDSTATS_SUMMARY $BUILDSTATS_PATH
    fi
fi
