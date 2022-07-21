#!/usr/bin/env bash
# Copyright (c) 2022 Foundries.io,
# SPDX-License-Identifier: Apache-2.0
set -o errexit
set -o pipefail

HERE=$(dirname $(readlink -f $0))
. $HERE/../helpers.sh


status Doing docker-login to hub.foundries.io with secret
docker login hub.foundries.io --username=doesntmatter --password="$(cat "/secrets/osftok")" | indent

export PYTHONPATH=${HERE}/../
python3 -c 'from apps.publish_manifest_lists import publish_manifest_lists; publish_manifest_lists("lmp")'
