#!/usr/bin/env bash
# Copyright (c) 2022 Foundries.io
# SPDX-License-Identifier: Apache-2.0

set -o errexit
set -o pipefail

HERE="$(dirname $(readlink -f $0))"
. "$HERE/../helpers.sh"

SECRETS=${SECRETS-/secrets}
TOKEN_FILE=${TOKEN_FILE-"${SECRETS}/osftok"}
DST_DIR=${SOTA_TUF_ROOT_DIR-usr/lib/sota/tuf}

require_params FACTORY TOKEN_FILE DST_DIR

PYTHONPATH=${HERE}/../ "${HERE}/fetch_root_meta.py" \
    --factory "${FACTORY}" \
    --token-file "${TOKEN_FILE}" \
    --dst-dir "${DST_DIR}" \
    --log-file "${LOG_FILE}"
