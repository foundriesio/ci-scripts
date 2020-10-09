#!/usr/bin/env bash
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

# Examples
# Container build's assemble-system-image use-case: ./tests/test_image_assembling.sh $FACTORY $OSF_TOKEN $OUT_IMAGE_DIR $BUILD_NUMB
# API/fioctl use-cases:
# all apps: ./tests/test_image_assembling.sh $FACTORY $OSF_TOKEN /home/mike/work/foundries/projects/ci-scripts/out-image/ "" raspberrypi3-64-lmp-41
# apps shortlisting: ./tests/test_image_assembling.sh $FACTORY $OSF_TOKEN /home/mike/work/foundries/projects/ci-scripts/out-image/ "" raspberrypi3-64-lmp-41 app-05

# Input params
FACTORY=$1
OSF_TOKEN=$2
OUT_IMAGE_DIR=$3
TARGET_VERSION=$4
TARGETS=${5-""}
APP_SHORTLIST=${6-""}

WORK_DIR="$(mktemp -d -t asseble-image-XXXXXXXXXX)"
echo ">> Work dir: ${WORK_DIR}"

SECRETS=$WORK_DIR/secrets # directory to store secrets,
#    - /secrets/osftok - file containing OSF_TOKEN
if [[ ! -d ${SECRETS} ]]; then
  mkdir "${SECRETS}"
fi
echo -n "${OSF_TOKEN}" > "${WORK_DIR}/secrets/osftok"

APP_IMAGE_DIR="${WORK_DIR}/app-images"
if [[ ! -d ${APP_IMAGE_DIR} ]]; then
  mkdir "${APP_IMAGE_DIR}"
fi

CMD=./assemble-system-image.sh

docker run -v -it --rm --privileged \
  -e FACTORY="$FACTORY" \
  -e APP_IMAGE_DIR=/app-images \
  -e OUT_IMAGE_DIR=/out-image-dir \
  -e TARGET_VERSION="${TARGET_VERSION}" \
  -e TARGETS="${TARGETS}" \
  -e APP_SHORTLIST="${APP_SHORTLIST}" \
  -v "$PWD":/ci-scripts \
  -v "$SECRETS":/secrets \
  -v "$APP_IMAGE_DIR":/app-images \
  -v "$OUT_IMAGE_DIR":/out-image-dir \
  -w /ci-scripts \
  -u "$(id -u ${USER})":"$(id -g ${USER})" \
  foundries/lmp-image-tools "${CMD}"
