#!/usr/bin/env bash
# Copyright (c) 2022 Foundries.io
# SPDX-License-Identifier: Apache-2.0

set -o errexit
set -o pipefail

HERE="$(dirname $(readlink -f $0))"
. "$HERE/helpers.sh"

require_params TARGET_JSON_FILE OCI_STORE_PATH TOKEN_FILE

"${HERE}/preload_apps.py" \
    --target-json-file "${TARGET_JSON_FILE}" \
    --app-shortlist "${APP_SHORTLIST}" \
    --oci-store-path "${OCI_STORE_PATH}" \
    --token-file "${TOKEN_FILE}" \
    --registry-creds "${REGISTRY_SECRETS}" \
    --log-file "${LOG_FILE}"
