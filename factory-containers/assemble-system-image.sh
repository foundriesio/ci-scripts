#!/usr/bin/env bash
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

set -o errexit
set -o pipefail

HERE=$(dirname $(readlink -f $0))
. $HERE/../helpers.sh

require_params FACTORY TOKEN_FILE APP_IMAGE_DIR OUT_IMAGE_DIR

export PYTHONPATH=${HERE}/../
status Running: Assemble System Image script

/usr/local/bin/dind ${HERE}/assemble-system-image.py 2>&1 | indent
