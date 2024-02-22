#!/usr/bin/env bash
# Copyright (c) 2024 Foundries.io
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

FACTORY=$1
TOKEN_FILE=$2
TARGETS_FILE=$3
FETCH_DIR=$4
DST_DIR=$5
APPS_SHORTLIST=${6-""}
API_HOST=${7-"api.foundries.io"}

CMD=./apps/fetch.py
PARAMS="\
  --factory=${FACTORY} \
  --targets-file=${TARGETS_FILE} \
  --token-file=${TOKEN_FILE} \
  --fetch-dir=/fetched-apps \
  --apps-shortlist=${APPS_SHORTLIST} \
  --dst-dir=/dst-dir \
"

docker run -v -it --rm \
  -e PYTHONPATH=. \
  -e H_RUN_URL="https://${API_HOST}" \
  -v "${PWD}":/ci-scripts \
  -v "${FETCH_DIR}":/fetched-apps \
  -v "${DST_DIR}":/dst-dir \
  -v "${TOKEN_FILE}":"${TOKEN_FILE}" \
  -v "${TARGETS_FILE}":"${TARGETS_FILE}" \
  -w /ci-scripts \
  foundries/lmp-image-tools ${CMD} ${PARAMS}