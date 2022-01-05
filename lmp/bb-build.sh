#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params IMAGE

start_ssh_agent

source setup-environment build

bitbake -D ${IMAGE}

bitbake -e | grep "^DEPLOY_DIR="| cut -d'=' -f2 | tr -d '"' > deploy_dir
