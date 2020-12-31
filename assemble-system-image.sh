#!/usr/bin/env bash
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

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
APPS_OSTREE_REPO_ARCHIVE_DIR="${APPS_OSTREE_REPO_ARCHIVE_DIR-/var/cache/bitbake/app-images/}"
APP_SHORTLIST="${APP_SHORTLIST-""}"
OSTREE_REPO_DIR="${OSTREE_REPO_DIR-$(mktemp -d)}"
# directory to preload/dump/snapshot apps images to
FETCH_DIR="${FETCH_DIR-$(mktemp -u -d)}"

require_params FACTORY APPS_OSTREE_REPO_ARCHIVE_DIR OUT_IMAGE_DIR
if [ -z "${TARGETS}" ] && [ -z "${TARGET_VERSION}" ]; then
  echo "Neither Target name list (TARGETS) nor Target version (aka H_BUILD) are specified !!!"
  exit 1
fi

export PYTHONPATH=${HERE}
status Running: Assemble System Image script

/usr/local/bin/dind "${HERE}/assemble.py" \
  --factory "${FACTORY}" \
  --token "$(cat "${SECRETS}/osftok")" \
  --target-version "${TARGET_VERSION}" \
  --out-image-dir "${OUT_IMAGE_DIR}" \
  --ostree-repo-archive-dir "${APPS_OSTREE_REPO_ARCHIVE_DIR}" \
  --repo-dir "${OSTREE_REPO_DIR}" \
  --fetch-dir "${FETCH_DIR}" \
  --targets "${TARGETS}" \
  --app-shortlist="${APP_SHORTLIST}"
