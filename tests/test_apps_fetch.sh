#!/usr/bin/env bash
# Copyright (c) 2024 Foundries.io
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

FACTORY=$1
TOKEN_FILE=$2
TARGETS=$3
DST_DIR=$4
APPS_SHORTLIST=$5
API_HOST=${6-"api.foundries.io"}

CMD=./apps/fetch.py
PARAMS="\
  --factory=${FACTORY} \
  --targets=${TARGETS} \
  --token-file=${TOKEN_FILE} \
  --dst-dir=/fetched-apps \
  --apps-shortlist=${APPS_SHORTLIST}
"

docker run -v -it --rm \
  -e PYTHONPATH=. \
  -e H_RUN_URL="https://${API_HOST}" \
  -v "${PWD}":/ci-scripts \
  -v "${DST_DIR}":/fetched-apps \
  -v "${TOKEN_FILE}":"${TOKEN_FILE}" \
  -w /ci-scripts \
  foundries/lmp-image-tools ${CMD} ${PARAMS}