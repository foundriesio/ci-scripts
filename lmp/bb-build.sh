#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params IMAGE

start_ssh_agent

source setup-environment build

# Parsing first, to abort in case of parsing issues
bitbake -p

# Global and image specific envs
bitbake -e > ${archive}/bitbake_global_env.txt
bitbake -e ${IMAGE} > ${archive}/bitbake_image_env.txt

bitbake -D ${IMAGE}
