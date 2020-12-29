#!/usr/bin/env bash
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

# examples
sudo ./tests/test_apps_fetcher.sh $FACTORY $OSF_TOKEN intel-corei7-64-lmp-275 $PWD/preload-dir $PWD/out-images

# Input params
FACTORY=$1
OSF_TOKEN=$2
TARGETS=$3
PRELOAD_DIR=$4
OUT_IMAGES_ROOT_DIR=$5

CMD="./apps/fetch.py"

docker run -it --rm --privileged \
  -e PYTHONPATH=/ci-scripts \
  -v $PWD:/ci-scripts \
  -v $PRELOAD_DIR:/preload \
  -v $OUT_IMAGES_ROOT_DIR:/out-image \
  -w /ci-scripts \
  -u $(id -u ${USER}):$(id -g ${USER}) \
  foundries/lmp-image-tools ${CMD} \
  --factory "${FACTORY}" \
  --token "${OSF_TOKEN}" \
  --target "${TARGETS}" \
  --preload-dir /preload \
  --out-images-root-dir /out-image

