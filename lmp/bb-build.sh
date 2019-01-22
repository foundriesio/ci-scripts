#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params IMAGE

source setup-environment build

bitbake -c cleanall aktualizr

bitbake ${IMAGE}

bitbake -e | grep "^DEPLOY_DIR_IMAGE="| cut -d'=' -f2 | tr -d '"' > image_dir
