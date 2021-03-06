#!/usr/bin/env bash
# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0
set -euo pipefail

# examples
# sudo is required for apps/containers images dumping
# sudo ./tests/test_apps_publishing.sh $FACTORY $OSF_TOKEN $FIO_USER_ID $FACTORY_CREDS $FACTORY_DIR/containers.git master

REQ_ARG_NUMB=5
if [[ $# -lt ${REQ_ARG_NUMB} ]]; then
    echo "Insufficient number of parameters"
    exit 1
fi

# Input params
FACTORY=$1
OSF_TOKEN=$2

# jobserv-curl -s https://api.foundries.io/ota/factories/msul-dev01/users/ | jq ".[0].\"polis-id\""
USER_ID=$3

# how to download it for average user??
CREDS_ARCH=$4

# a full path to containers.git repo
APPS_ROOT_DIR=$5

APPS_OSTREE_REPO_ARCHIVE_DIR=$6

# A tag to apply to newly created Target(s), optional, master by default
OTA_LITE_TAG=${7-"master"}

# a dir where the updated creds.zip will be stored along with Factory's TUF repo (keys, targets, etc), optional
WORK_DIR=${8-"$(mktemp -d -t publish-compose-app-XXXXXXXXXX)"}
echo ">> Work dir: ${WORK_DIR}"

# MACHINES to create Targets for, optional, by default, if not specified, Targets for all MACHINES
# found in the previous Targets will be created
MACHINES=${9-""}

# PLATFORMS to create Targets for, optional, if not defined `container` Target will be created for each
# found previous Targets
PLATFORMS=${10-""}

# Indicates whether to push the new Target(s) to the Factory's TUF repo, optional, off by default
PUSH_TARGET=${11-""}

# a path to the compose publish binary tool, optional, will be downloaded if not specified
PUBLISH_TOOL=${12-""}


ARCHIVE=$WORK_DIR/archive # directory to store artifacts generated by the given script/job
if [[ ! -d ${ARCHIVE} ]]; then
  mkdir "${ARCHIVE}"
fi

SECRETS=$WORK_DIR/secrets # directory to store secrets,
#    - /secrets/osftok - file containing OSF_TOKEN
#    - /secrets/triggered-by - just client_ID from credentials.zip:treehub.json:oauth2:client_id
#    - /secrets/credentials.zip - you Factory OTA creds, created on the first Factory's build
if [[ ! -d ${SECRETS} ]]; then
  mkdir "${SECRETS}"
fi

echo -n "${OSF_TOKEN}" > "${WORK_DIR}/secrets/osftok"
echo -n "${USER_ID}" > "${WORK_DIR}/secrets/triggered-by"

TUF_REPO=$WORK_DIR/tuf-repo # directory for TUF metadata files, must be created by current user

if [[ ! -d ${TUF_REPO} ]]; then
  mkdir "${TUF_REPO}"
fi

APP_IMAGES_ROOT_DIR="${WORK_DIR}/app-images"
if [[ ! -d ${APP_IMAGES_ROOT_DIR} ]]; then
  mkdir "${APP_IMAGES_ROOT_DIR}"
fi

FETCH_DIR="${APP_IMAGES_ROOT_DIR}/fetch-dir"
if [[ ! -d ${FETCH_DIR} ]]; then
  mkdir "${FETCH_DIR}"
fi

OSTREE_REPO_DIR="${APP_IMAGES_ROOT_DIR}/ostree-repo-dir"
if [[ ! -d ${OSTREE_REPO_DIR} ]]; then
  mkdir "${OSTREE_REPO_DIR}"
fi

TREEHUB_REPO_DIR="${APP_IMAGES_ROOT_DIR}/treehub-repo-dir"
if [[ ! -d ${TREEHUB_REPO_DIR} ]]; then
  mkdir "${TREEHUB_REPO_DIR}"
fi

CMD=./apps/publish.sh

docker run -v -it --rm --privileged \
  -e FACTORY=$FACTORY \
  -e CREDS_ARCH=/secrets/credentials.zip \
  -e CREDS_ARCH_UPDATED=/secrets/credentials-updated.zip \
  -e TUF_REPO="/tuf-repo/$FACTORY" \
  -e OTA_LITE_TAG=$OTA_LITE_TAG \
  -e COMPOSE_APP_USE_OSTREE="1" \
  -e APPS_ROOT_DIR=/apps \
  -e PUBLISH_TOOL=/usr/local/bin/compose-publish \
  -e PUSH_TARGETS=$PUSH_TARGET \
  -e FETCH_DIR=/fetch-dir \
  -e OSTREE_REPO_DIR=/ostree-repo-dir \
  -e TREEHUB_REPO_DIR=/treehub-repo-dir \
  -e APPS_OSTREE_REPO_ARCHIVE_DIR=/repo_archive_dir/ \
  -e HOME=/home/ \
  -e MACHINES="${MACHINES}" \
  -e MANIFEST_PLATFORMS_DEFAULT="${PLATFORMS}" \
  -v $PWD:/ci-scripts \
  -v $ARCHIVE:/archive \
  -v $SECRETS:/secrets \
  -v $TUF_REPO:/tuf-repo \
  -v $APPS_ROOT_DIR:/apps \
  -v $PUBLISH_TOOL:/usr/local/bin/compose-publish \
  -v $CREDS_ARCH:/secrets/credentials.zip \
  -v $APPS_OSTREE_REPO_ARCHIVE_DIR:/repo_archive_dir \
  -v $FETCH_DIR:/fetch-dir \
  -v $OSTREE_REPO_DIR:/ostree-repo-dir \
  -v $TREEHUB_REPO_DIR:/treehub-repo-dir \
  -w /ci-scripts \
  -u $(id -u ${USER}):$(id -g ${USER}) \
  foundries/lmp-image-tools "${CMD}"

if [[ $? -eq 0 ]]; then
  echo "Your apps has been successfully published, see the work dir for details: ${WORK_DIR}"
else
  echo "Failed to publish Compose Apps"
fi
