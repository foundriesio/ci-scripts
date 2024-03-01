#!/usr/bin/env bash
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: BSD-3-Clause

set -o errexit
set -o pipefail

HERE="$(dirname $(readlink -f $0))"
. "$HERE/helpers.sh"

SECRETS=${SECRETS-/secrets}
# if the container is started with `-u $(id -u ${USER}):$(id -g ${USER})` then HOME='/'
if [ "${HOME}" = "/" ]; then
  HOME="/root"
fi
TARGETS="${TARGETS}"
TARGET_VERSION="${TARGET_VERSION-${H_BUILD}}"
# destination for a resultant system image
OUT_IMAGE_DIR="${OUT_IMAGE_DIR-/archive}"
APP_SHORTLIST="${APP_SHORTLIST-""}"
COMPOSE_APP_TYPE=${COMPOSE_APP_TYPE-""}
# directory to preload/dump/snapshot apps images to
FETCH_DIR="${FETCH_DIR-$(mktemp -u -d -p /var/cache/apps)}"

require_params FACTORY OUT_IMAGE_DIR
if [ -z "${TARGETS}" ] && [ -z "${TARGET_VERSION}" ]; then
  echo "Neither Target name list (TARGETS) nor Target version (aka H_BUILD) are specified !!!"
  exit 1
fi

load_extra_certs

if [ -f /secrets/container-registries ] ; then
	PYTHONPATH=$HERE $HERE/apps/login_registries /secrets/container-registries
fi

export PYTHONPATH=${HERE}
status Running: Assemble System Image script

/usr/local/bin/dind "${HERE}/assemble.py" \
  --factory "${FACTORY}" \
  --token "$(cat "${SECRETS}/osftok")" \
  --target-version "${TARGET_VERSION}" \
  --out-image-dir "${OUT_IMAGE_DIR}" \
  --fetch-dir "${FETCH_DIR}" \
  --targets "${TARGETS}" \
  --app-shortlist="${APP_SHORTLIST}" \
  --app-type="${COMPOSE_APP_TYPE}"
