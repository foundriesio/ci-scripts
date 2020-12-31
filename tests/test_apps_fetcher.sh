#!/usr/bin/env bash
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

# examples
# sudo ./tests/test_apps_fetcher.sh $FACTORY $OSF_TOKEN $FACTORY_CREDS intel-corei7-64-lmp-284 $PWD/work-dir/ $PWD/arch-repo-dir/

# Input params
FACTORY=$1
OSF_TOKEN=$2
CRED_ARCH=$3
TARGETS=$4
WORK_DIR=$5
IN_OUT_REPO_ARCH_DIR=$6

CMD="./apps/fetch.py"

docker run -it --rm --privileged \
  -e CRED_ARCH=/secrets/credentials.zip \
  -v $CRED_ARCH:/secrets/credentials.zip \
  -v $PWD:/ci-scripts \
  -v $IN_OUT_REPO_ARCH_DIR:/nfs \
  -v $WORK_DIR:/work-dir \
  -w /ci-scripts \
  -u $(id -u ${USER}):$(id -g ${USER}) \
  -e PYTHONPATH=/ci-scripts \
  foundries/lmp-image-tools ${CMD} \
  --factory "${FACTORY}" \
  --token "${OSF_TOKEN}" \
  --targets "${TARGETS}" \
  --cred-arch /secrets/credentials.zip \
  --fetch-dir /work-dir/fetch-dir \
  --treehub-repo /work-dir/treehub-repo \
  --repo-dir /work-dir/repo-dir \
  --ostree-repo-archive-dir /nfs/

