#!/usr/bin/env bash
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

# Examples
# sudo ./tests/test_apps_publishing_to_ostree.sh $FACTORY $OSF_TOKEN $FACTORY_CREDS tuf/tuf-repo/roles/unsigned/targets.json targets-created-msul-dev02.json fetch-dir/ repo-dir/

# Input params
FACTORY=$1
OSF_TOKEN=$2
CRED_ARCH_FILE=$3
ALL_TARGETS=$4
TARGETS_TO_PUBLISH=$5
FETCH_DIR=$6
REPO_DIR=$7

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
  --targets-file "${ALL_TARGETS}" \
  --targets-to-publish "${TARGETS_TO_PUBLISH}" \
  --fetch-dir "${FETCH_DIR}" \
  --repo-dir "${REPO_DIR}"
