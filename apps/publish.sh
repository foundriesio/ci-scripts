#!/usr/bin/env bash
# Copyright (c) 2020 Foundries.io,
# SPDX-License-Identifier: Apache-2.0
set -o errexit
set -o pipefail

HERE=$(dirname $(readlink -f $0))
. $HERE/../helpers.sh


#-- BEGIN: Input params
ARCHIVE=${ARCHIVE-/archive}
SECRETS=${SECRETS-/secrets}
# if the container is started with `-u $(id -u ${USER}):$(id -g ${USER})` then HOME='/'
if [ "${HOME}" = "/" ]; then
  HOME="/root"
fi
# Do not store TUF_REPO in /tmp since it's remounted by dind and the repo/targets.json is removed otherwise
TUF_REPO="${TUF_REPO-$(mktemp -u -d -p ${HOME})}"
# OTA_LITE_TAG and TARGET_TAG is the same tag, effectively this is a tag to apply to new Target(s)
# that are created by a given build
TARGET_TAG=${OTA_LITE_TAG}

DOCKER_COMPOSE_APP_PRELOAD=${DOCKER_COMPOSE_APP_PRELOAD-""}
COMPOSE_APP_USE_OSTREE=${COMPOSE_APP_USE_OSTREE-""}

APPS_ROOT_DIR=${APPS_ROOT_DIR-${PWD}}
PUBLISH_TOOL=${PUBLISH_TOOL-""}

APPS_VERSION=${H_BUILD}_${APPS_VERSION-$(git --git-dir="${APPS_ROOT_DIR}/.git" log -1 --format=%h)}
GIT_SHA=${GIT_SHA-$(git --git-dir="${APPS_ROOT_DIR}/.git" log -1 --format=%H)}
TARGET_VERSION=${H_BUILD-""}

CREDS_ARCH_UPDATED=${CREDS_ARCH_UPDATED-$(mktemp -p ${HOME})}
PUSH_TARGETS=${PUSH_TARGETS-true}

MACHINES=${MACHINES-""}
PLATFORMS=${MANIFEST_PLATFORMS_DEFAULT-""}

APP_IMAGES_ROOT_DIR="${APP_IMAGES_ROOT_DIR-/var/cache/bitbake/app-images}"
APPS_OSTREE_REPO_ARCHIVE_DIR="${APPS_OSTREE_REPO_ARCHIVE_DIR-/var/cache/bitbake/app-images/}"
OSTREE_REPO_DIR="${OSTREE_REPO_DIR-$(mktemp -d -p ${HOME})}"
TREEHUB_REPO_DIR="${TREEHUB_REPO_DIR-$(mktemp -d -p ${HOME})}"
FETCH_DIR="${FETCH_DIR-$(mktemp -u -d)}"
APP_SHORTLIST="${APP_SHORTLIST-""}"

require_params FACTORY ARCHIVE TARGET_TAG
#-- END: Input params

pbc=pre-build.conf
if [ -f $pbc ] ; then
  echo "Sourcing pre-build.conf."
  . $pbc
fi

if [ -f /secrets/container-registries ] ; then
	PYTHONPATH=$HERE/.. $HERE/login_registries /secrets/container-registries
fi

status Doing docker-login to hub.foundries.io with secret
docker login hub.foundries.io --username=doesntmatter --password="$(cat "${SECRETS}/osftok")" | indent

if [ ! -f "${PUBLISH_TOOL}" ]; then
  status Dowloading "compose-ref (aka compose-publish)" for publishing apps
  PUBLISH_TOOL="/tmp/compose-publish"
  run wget -O ${PUBLISH_TOOL} https://storage.googleapis.com/subscriber_registry/compose-publish-with-layers
  chmod +x ${PUBLISH_TOOL}
fi

export PYTHONPATH=${HERE}/../

"$HERE"/../create-creds "${CREDS_ARCH_UPDATED}"
export TAG=$(git log -1 --format=%h)

if [ ! -f "${TUF_REPO}/credentials.zip" ]; then
  status "Initializing directory for TUF metadata: ${TUF_REPO}"
  run garage-sign init --repo "${TUF_REPO}" --credentials "${CREDS_ARCH_UPDATED}"
fi

status "Pulling TUF Targets of Factory ${FACTORY} to ${TUF_REPO}"
run garage-sign targets pull --repo "${TUF_REPO}"
cp "${TUF_REPO}/roles/unsigned/targets.json" "${ARCHIVE}/targets-before.json"

# The following does
# 1. publish apps (obviously apps' container images must be built and published before it)
#   - tag images listed in docker-compose.yaml and built by Factory so they point to the images
#     built by the given container build. The tag is an abbreviated commit hash to containers.git
#   - call the compose app publish tool that
#     - pin all images in docker-compose.yml with corresponding SHA, sha256 of images manifest (python code could do it)
#     - create archive containing App files, create manifest for it and uploads to Docker Registry (could be done in Python)
#
# 2. create new Targets and adds them to targets.json
status "Publishing apps; version: ${APPS_VERSION}, Target tag: ${TARGET_TAG}"

"${HERE}/publish.py" \
    --factory "${FACTORY}" \
    --targets "${TUF_REPO}/roles/unsigned/targets.json" \
    --machines "${MACHINES}" \
    --platforms "${PLATFORMS}" \
    --apps-root-dir "${APPS_ROOT_DIR}" \
    --publish-tool "${PUBLISH_TOOL}" \
    --apps-version "${APPS_VERSION}" \
    --target-tag "${TARGET_TAG}" \
    --git-sha "${GIT_SHA}" \
    --target-version="${TARGET_VERSION}" \
    --new-targets-file="${ARCHIVE}/targets-created.json"

if [ "${COMPOSE_APP_USE_OSTREE}" = "1" ]; then
  # If OSTree usage is enabled then apps have to be fetched regardless of DOCKER_COMPOSE_APP_PRELOAD is on or off
  # because apps data/files have to be put into an ostree repo and pushed to Treehub so aklite can fetch them and update
  # apps on a device. Also, the resultant apps ostree repo can used during LmP build for preloading.
  #
  # 1. Copy and untar the archive containing an ostree repo with apps and their images, if exists
  # 2. Dump Targets' Apps and their images (it pulls just apps' diff)
  # 3. Commit Targets' Apps and their images to the ostree repo
  # 4. Push the Target's commit to Treehub
  # 5. Archive and copy the updates apps' ostree repo to NFS/shared storage
  /usr/local/bin/dind "${HERE}/publish_apps_to_ostree.py" \
    --factory "${FACTORY}" \
    --token "$(cat "${SECRETS}/osftok")" \
    --cred-arch "${CREDS_ARCH_UPDATED}" \
    --targets-file "${TUF_REPO}/roles/unsigned/targets.json" \
    --targets-to-publish "${ARCHIVE}/targets-created.json" \
    --fetch-dir "${FETCH_DIR}" \
    --repo-dir "${OSTREE_REPO_DIR}" \
    --treehub-repo-dir "${TREEHUB_REPO_DIR}" \
    --ostree-repo-archive-dir "${APPS_OSTREE_REPO_ARCHIVE_DIR}"
fi

cp "${TUF_REPO}/roles/unsigned/targets.json" "${ARCHIVE}/targets-after.json"

echo "Signing local TUF targets"
run garage-sign targets sign --repo "${TUF_REPO}" --key-name targets

if [ "${PUSH_TARGETS}" ]; then
  echo "Publishing local TUF targets to the remote TUF repository"
  run garage-sign targets push --repo "${TUF_REPO}"
fi
