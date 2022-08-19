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
