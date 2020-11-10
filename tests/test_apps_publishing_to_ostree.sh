#!/usr/bin/env bash
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

# Input params
FACTORY=$1
OSF_TOKEN=$2
CRED_ARCH_FILE=$3
TARGETS=$4
FETCH_DIR=$5
REPO_DIR=$6

CMD="/usr/local/bin/dind ./apps/publish_apps_to_ostree.py"

docker run -it --rm --privileged \
  -e PYTHONPATH=/ci-scripts \
  -v $PWD:/ci-scripts \
  -v $CRED_ARCH_FILE:/credentials.zip \
  -w /ci-scripts \
  -u $(id -u ${USER}):$(id -g ${USER}) \
  foundries/lmp-image-tools ${CMD} \
  --factory "${FACTORY}" \
  --token "${OSF_TOKEN}" \
  --cred-arch "/credentials.zip" \
  --targets "${TARGETS}" \
  --fetch-dir "${FETCH_DIR}" \
  --repo-dir "${REPO_DIR}"
