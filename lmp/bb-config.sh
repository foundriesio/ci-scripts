#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params MACHINE IMAGE

OSTREE_BRANCHNAME="${OSTREE_BRANCHNAME-lmp-localdev}"
SOTA_CLIENT="${SOTA_CLIENT-aktualizr}"
AKLITE_TAG="${AKLITE_TAG-promoted}"
H_BUILD="${H_BUILD-lmp-localdev}"
LMP_VERSION=$(git --git-dir=.repo/manifests/.git describe --tags 2>/dev/null || echo unknown)
FACTORY="${FACTORY-lmp}"
UBOOT_SIGN_ENABLE="${UBOOT_SIGN_ENABLE-0}"
ENABLE_PTEST="${ENABLE_PTEST-0}"
DOCKER_MAX_CONCURRENT_DOWNLOADS="${DOCKER_MAX_CONCURRENT_DOWNLOADS-3}"
DOCKER_MAX_DOWNLOAD_ATTEMPTS="${DOCKER_MAX_DOWNLOAD_ATTEMPTS-5}"

GARAGE_CUSTOMIZE_TARGET_PARAMS='${MACHINE} ${IMAGE_BASENAME} ${TARGET_ARCH}'

if [ "$ENABLE_PTEST" = "1" ] ; then
    OSTREE_BRANCHNAME="${OSTREE_BRANCHNAME}-ptest"
fi

source setup-environment build

cat << EOFEOF >> conf/local.conf
CONNECTIVITY_CHECK_URIS = "https://www.google.com/"

ACCEPT_FSL_EULA = "1"
BB_GENERATE_MIRROR_TARBALLS = "1"

UBOOT_SIGN_ENABLE = "${UBOOT_SIGN_ENABLE}"

# SOTA params
SOTA_PACKED_CREDENTIALS = "${SOTA_PACKED_CREDENTIALS}"
OSTREE_BRANCHNAME = "${MACHINE}-${OSTREE_BRANCHNAME}"
GARAGE_SIGN_REPO = "/tmp/garage_sign_repo"
GARAGE_TARGET_VERSION = "${H_BUILD}"
GARAGE_TARGET_URL = "https://ci.foundries.io/projects/${H_PROJECT}/builds/${H_BUILD}"
GARAGE_CUSTOMIZE_TARGET = "${HERE}/customize-target ${GARAGE_CUSTOMIZE_TARGET_PARAMS}"
DOCKER_COMPOSE_APP = "${DOCKER_COMPOSE_APP}"
APP_IMAGES_PRELOADER = "${HERE}/preload-app-images"
DOCKER_COMPOSE_APP_PRELOAD = "${DOCKER_COMPOSE_APP_PRELOAD}"

# Default SOTA client
SOTA_CLIENT = "${SOTA_CLIENT}"

# git-describe version of LMP
LMP_VERSION = "${LMP_VERSION}"

# Default AKLITE tag
AKLITE_TAG = "${AKLITE_TAG}"

# Who's factory is this?
export FOUNDRIES_FACTORY = "${FACTORY}"

# Additional packages based on the CI job used
IMAGE_INSTALL_append = " ${EXTRA_IMAGE_INSTALL}"

# dockerd params
DOCKER_MAX_CONCURRENT_DOWNLOADS = "${DOCKER_MAX_CONCURRENT_DOWNLOADS}"
DOCKER_MAX_DOWNLOAD_ATTEMPTS = "${DOCKER_MAX_DOWNLOAD_ATTEMPTS}"
EOFEOF

if [ -n "$OTA_LITE_TAG" ] ; then
	# Ptest-based builds require the same build settings and variables,
	# but the final image needs to be tagged differently, such as
	# <main tag>-ptest, so perform the change at the OTA_LITE_TAG variable
	if [ "${ENABLE_PTEST}" = "1" ]; then
		IFS=","
		PTAGS=""
		for tag in ${OTA_LITE_TAG}; do
			lmptag=$(echo $tag | cut -d: -f1)
			PTAGS="${PTAGS} ${lmptag}-ptest"
			contag=$(echo $tag | cut -s -d: -f1 --complement)
			if [ -n "${contag}" ]; then
				PTAGS="${PTAGS}:${contag}"
			fi
		done
		unset IFS
		OTA_LITE_TAG=$(echo ${PTAGS} | sed -e "s/ /,/g")
		status "PTEST enabled, OTA_LITE_TAG updated to: ${OTA_LITE_TAG}"

		# Install ptest related packages via extra image features
		cat << EOFEOF >> conf/local.conf
EXTRA_IMAGE_FEATURES += " ptest-pkgs"
EOFEOF
	fi

	cat << EOFEOF >> conf/local.conf
export OTA_LITE_TAG = "${OTA_LITE_TAG}"
# Take a tag from a spec like:
#  https://docs.foundries.io/latest/reference/advanced-tagging.html
# and find the first tag name to produce a senible default
LMP_DEVICE_REGISTER_TAG = "$(echo ${OTA_LITE_TAG} | cut -d: -f1 | cut -d, -f1)"
EOFEOF
fi

if [ -z "$SOTA_PACKED_CREDENTIALS" ] || [ ! -f $SOTA_PACKED_CREDENTIALS ] ; then
	status "SOTA_PACKED_CREDENTIALS not found, disabling OSTree publishing logic"
	cat << EOFEOF >> conf/local.conf
SOTA_PACKED_CREDENTIALS = ""
EOFEOF
fi

# Add build id H_BUILD to output files names
cat << EOFEOF >> conf/auto.conf
IMAGE_NAME_append = "-${H_BUILD}"
KERNEL_IMAGE_BASE_NAME_append = "-${H_BUILD}"
MODULE_IMAGE_BASE_NAME_append = "-${H_BUILD}"
DT_IMAGE_BASE_NAME_append = "-${H_BUILD}"
BOOT_IMAGE_BASE_NAME_append = "-${H_BUILD}"
DISTRO_VERSION_append = "-${H_BUILD}-${LMP_VERSION}"

# get build stats to make sure that we use sstate properly
INHERIT += "buildstats buildstats-summary"

# archive sources for target recipes (for license compliance)
INHERIT += "archiver"
COPYLEFT_RECIPE_TYPES = "target"
ARCHIVER_MODE[src] = "original"
ARCHIVER_MODE[diff] = "1"
EOFEOF

if [ $(ls ../sstate-cache | wc -l) -ne 0 ] ; then
	status "Found existing sstate cache, using local copy"
	echo 'SSTATE_MIRRORS = ""' >> conf/auto.conf
fi

for x in $(ls conf/*.conf) ; do
	status "$x"
	cat $x | indent
done
