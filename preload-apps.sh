#!/usr/bin/env bash
# Copyright (c) 2022 Foundries.io
# SPDX-License-Identifier: BSD-3-Clause

set -o errexit
set -o pipefail

HERE="$(dirname $(readlink -f $0))"
. "$HERE/helpers.sh"

require_params TARGET_JSON_FILE OCI_STORE_PATH TOKEN_FILE

# Create a temporal file for `skopeo` to store auth material in.
# The file is removed once preloading is completed.
# Also, we need to add an empty json `{}` to it, otherwise `skopeo login` fails
export REGISTRY_AUTH_FILE=$(mktemp)
echo "{}" > "${REGISTRY_AUTH_FILE}"

PATH="${PATH}:/usr/bin" "${HERE}/preload_apps.py" \
    --target-json-file "${TARGET_JSON_FILE}" \
    --app-shortlist "${APP_SHORTLIST}" \
    --oci-store-path "${OCI_STORE_PATH}" \
    --token-file "${TOKEN_FILE}" \
    --registry-creds-file "${REGISTRY_SECRETS_FILE}" \
    --log-file "${LOG_FILE}"

trap 'rm -f "${REGISTRY_AUTH_FILE}"' INT TERM HUP EXIT
