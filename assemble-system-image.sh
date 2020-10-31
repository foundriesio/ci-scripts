#!/usr/bin/env bash
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

set -o errexit
set -o pipefail

HERE="$(dirname $(readlink -f $0))"
. "$HERE/helpers.sh"

SECRETS=${SECRETS-/secrets}
TARGETS="${TARGETS}"
TARGET_VERSION="${TARGET_VERSION-${H_BUILD}}"
# destination for a resultant system image
OUT_IMAGE_DIR="${OUT_IMAGE_DIR-/archive}"
# a dir where snapshotted/dumped images (archive/tar) are supposed to be located
# if not found there assemble.py will dump images, archive them and put into the given location
APP_IMAGE_DIR="${APP_IMAGE_DIR-/var/cache/bitbake/app-images}"
APP_SHORTLIST="${APP_SHORTLIST-""}"
# directory to preload/dump/snapshot apps images to
PRELOAD_DIR="${PRELOAD_DIR-$(mktemp -u -d)}"

require_params FACTORY APP_IMAGE_DIR OUT_IMAGE_DIR
if [ -z "${TARGETS}" ] && [ -z "${TARGET_VERSION}" ]; then
  echo "Neither Target name list (TARGETS) nor Target version (aka H_BUILD) are specified !!!"
  exit 1
fi

export PYTHONPATH=${HERE}
status Running: Assemble System Image script

apk add tar

/usr/local/bin/dind "${HERE}/assemble.py" \
  --factory "${FACTORY}" \
  --token "$(cat "${SECRETS}/osftok")" \
  --target-version "${TARGET_VERSION}" \
  --out-image-dir "${OUT_IMAGE_DIR}" \
  --app-image-dir "${APP_IMAGE_DIR}" \
  --preload-dir "${PRELOAD_DIR}" \
  --targets "${TARGETS}" \
  --app-shortlist="${APP_SHORTLIST}"
