#!/bin/bash -e

function finish() {
    # save the return code
    rc=$?
    # allow this block to fail
    set +e

    status "Run bitbake (finish)"

    # we need to check that because it is not available before kirkstone
    if command -v bitbake-getvar >/dev/null 2>&1; then
        # get buildstats path
        BUILDSTATS_PATH="$(bitbake-getvar --value TMPDIR | tail -n 1)/buildstats"
    fi
    # check if the buildstats was enabled
    if [ -d "$BUILDSTATS_PATH" ]; then
        # get the most recent folder
        BUILDSTATS_PATH="$(ls -td -- $BUILDSTATS_PATH/*/ | head -n 1)"
        # we need to check that because it can't be available in old containers
        if command -v xvfb-run >/dev/null 2>&1 ; then
            # producing bootchart.svg
            xvfb-run $(realpath $BUILDDIR/../layers/openembedded-core/scripts/pybootchartgui/pybootchartgui.py) \
                --minutes --format=svg --output=${archive}/bitbake_buildchart $BUILDSTATS_PATH
        fi
        # write a summary of the buildstats to the terminal
        BUILDSTATS_SUMMARY="$(realpath $BUILDDIR/../layers/openembedded-core/scripts/buildstats-summary)"
        # we need to check that because it is only available in the kirkstone branch
        if [ -f $BUILDSTATS_SUMMARY ]; then
            # common arguments with bold disabled
            BUILDSTATS_SUMMARY="$BUILDSTATS_SUMMARY --sort duration --highlight 0"
            # log all task
            $BUILDSTATS_SUMMARY $BUILDSTATS_PATH > ${archive}/bitbake_buildstats.log
            # only run for successfully builds
            if [ "$rc" -eq "0" ]; then
                # for console hide tasks < Seconds
                BUILDSTATS_SUMMARY="$BUILDSTATS_SUMMARY --shortest 60"
                run $BUILDSTATS_SUMMARY $BUILDSTATS_PATH
            fi
        fi
    fi

    status "Run bitbake (rsync factory sstate-cache mirror)"
    SSTATE_DIR="$(grep "^SSTATE_DIR=" ${archive}/bitbake_global_env.txt | cut -d'=' -f2 | tr -d '"')"
    rsync -vv -a --copy-links --copy-dirlinks --hard-links ${SSTATE_DIR}/ ${FACTORY_SSTATE_CACHE_MIRROR}/ > ${archive}/bitbake_sstatemirror.log

    exit $rc
}

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params IMAGE

start_ssh_agent

source setup-environment build

# store bitbake-cookerdaemon log
ln -s ${archive}/bitbake_cookerdaemon.log bitbake-cookerdaemon.log

# Parsing first, to stop in case of parsing issues
status "Run bitbake (parsing)"
bitbake -p

# Global and image specific envs
status "Run bitbake (save the global and image specific environments)"
bitbake -e > ${archive}/bitbake_global_env.txt
bitbake -e ${IMAGE} > ${archive}/bitbake_image_env.txt

# Setscene (cache), failures not critical
status "Run bitbake (setscene tasks only)"
bitbake --setscene-only ${IMAGE} || true

# add trap to do some pending operations on exit
trap finish TERM INT EXIT

if [ "$BUILD_SDK" == "1" ] && [ "${DISTRO}" != "lmp-mfgtool" ]; then
    status "Run bitbake (populate sdk)"
    bitbake -D ${BITBAKE_EXTRA_ARGS} ${IMAGE} -c populate_sdk
fi
status "Run bitbake"
bitbake -D ${BITBAKE_EXTRA_ARGS} ${IMAGE}
