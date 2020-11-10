#!/usr/bin/env bash
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

# Input params
FACTORY=$1
OSF_TOKEN=$2
TARGETS=$3
PRELOAD_DIR=$4
OUT_IMAGES_ROOT_DIR=$5
#CRED_ARCH_DIR=$6

CMD="/usr/local/bin/dind ./apps/fetch.py"

docker run -it --rm --privileged \
  -e PYTHONPATH=/ci-scripts \
  -v $PWD:/ci-scripts \
  -w /ci-scripts \
  -u $(id -u ${USER}):$(id -g ${USER}) \
  foundries/lmp-image-tools ${CMD} \
  --factory "${FACTORY}" \
  --token "${OSF_TOKEN}" \
  --targets "${TARGETS}" \
  --preload-dir "${PRELOAD_DIR}" \
  --out-images-root-dir "${OUT_IMAGES_ROOT_DIR}"
   #\
  #--cred-arch "/cred_dir/credentials.zip"


