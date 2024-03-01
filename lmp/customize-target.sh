#!/usr/bin/env bash
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: BSD-3-Clause

set -o errexit
set -o pipefail

HERE=$(dirname $(readlink -f $0))
. $HERE/../helpers.sh

export PYTHONPATH=${HERE}/../
export MANIFEST_REPO='/srv/oe/.repo/manifests'
export META_SUB_OVERRIDES_REPO='/srv/oe/layers/meta-subscriber-overrides'

status Running: Customizing Target...
${HERE}/customize-target.py "$@" 2>&1 | indent
