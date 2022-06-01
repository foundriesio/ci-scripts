#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params IMAGE

start_ssh_agent

source setup-environment build

# Global and image specific envs and if not possible run the parsing to get the reason
bitbake -e > ${archive}/bitbake_global_env.txt && \
bitbake -e ${IMAGE} > ${archive}/bitbake_image_env.txt || \
bitbake -p

# Setscene (cache), failures not critical
bitbake --setscene-only ${IMAGE} || true

bitbake -D ${BITBAKE_EXTRA_ARGS} ${IMAGE}
