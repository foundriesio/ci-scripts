#!/usr/bin/env bash
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

set -o errexit
set -o pipefail

HERE="$(dirname $(readlink -f $0))"
. "$HERE/helpers.sh"

REGISTRY_SECRETS_FOLDER="${REGISTRY_SECRETS_FOLDER-/secrets/container-registries}"

require_params TARGET_JSON_FILE OCI_STORE_PATH TOKEN_FILE

if [ -f "${REGISTRY_SECRETS_FOLDER}" ]; then
  PYTHONPATH="${HERE}" "${HERE}/apps/login_registries" "${REGISTRY_SECRETS_FOLDER}"
fi

"${HERE}/preload_apps.py" \
    --target-json-file "${TARGET_JSON_FILE}" \
    --app-shortlist "${APP_SHORTLIST}" \
    --oci-store-path "${OCI_STORE_PATH}" \
    --token-file "${TOKEN_FILE}" \
    --log-file "${LOG_FILE}"
