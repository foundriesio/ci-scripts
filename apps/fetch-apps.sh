#!/usr/bin/env bash
# Copyright (c) 2022 Foundries.io
# SPDX-License-Identifier: Apache-2.0

set -o errexit
set -o pipefail

HERE="$(dirname $(readlink -f $0))"
. "$HERE/../helpers.sh"

SECRETS=${SECRETS-/secrets}
ARCHIVE=${ARCHIVE-/archive}
DST_DIR=${DST_DIR-"${ARCHIVE}/oci-store"}
TOKEN_FILE=${TOKEN_FILE-"${SECRETS}/osftok"}
REGISTRY_SECRETS_FILE=${REGISTRY_SECRETS_FILE-"${SECRETS}/container-registries"}

require_params TARGET_NAME FACTORY TOKEN_FILE DST_DIR

TAR_OUTPUT=${TAR_OUTPUT-"${ARCHIVE}/${TARGET_NAME}-apps.tar"}

if [ -f "${REGISTRY_SECRETS_FILE}" ] ; then
	PYTHONPATH=$HERE/.. $HERE/login_registries "${REGISTRY_SECRETS_FILE}"
fi

PYTHONPATH=${HERE}/../ "${HERE}/fetch_apps.py" \
    --target-name "${TARGET_NAME}" \
    --factory "${FACTORY}" \
    --token-file "${TOKEN_FILE}" \
    --dst-dir "${DST_DIR}" \
    --shortlist "${APP_SHORTLIST}"

if [ ! -z "${TAR_OUTPUT}" ]; then
  status "Tarring fetched Apps to ${TAR_OUTPUT}"
  tar -cf "${TAR_OUTPUT}" -C "${DST_DIR}" .
  rm -rf "${DST_DIR}"
fi