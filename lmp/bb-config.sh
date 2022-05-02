#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params MACHINE IMAGE OTA_LITE_TAG

OSTREE_BRANCHNAME="${OSTREE_BRANCHNAME-lmp-localdev}"
SOTA_CLIENT="${SOTA_CLIENT-aktualizr}"
AKLITE_TAG="${AKLITE_TAG-promoted}"
H_BUILD="${H_BUILD-lmp-localdev}"
LMP_VERSION=$(git --git-dir=.repo/manifests/.git describe --tags 2>/dev/null || echo unknown)
FACTORY="${FACTORY-lmp}"
LMP_DEVICE_API="${LMP_DEVICE_API-https://api.foundries.io/ota/devices/}"
UBOOT_SIGN_ENABLE="${UBOOT_SIGN_ENABLE-0}"
DISABLE_GPLV3="${DISABLE_GPLV3-0}"
ENABLE_PTEST="${ENABLE_PTEST-0}"
DOCKER_MAX_CONCURRENT_DOWNLOADS="${DOCKER_MAX_CONCURRENT_DOWNLOADS-3}"
DOCKER_MAX_DOWNLOAD_ATTEMPTS="${DOCKER_MAX_DOWNLOAD_ATTEMPTS-5}"
MFGTOOL_FLASH_IMAGE="${MFGTOOL_FLASH_IMAGE-lmp-factory-image}"
SSTATE_CACHE_MIRROR="${SSTATE_CACHE_MIRROR-/sstate-cache-mirror}"
USE_FIOTOOLS="${USE_FIOTOOLS-1}"
FIO_CHECK_CMD="${FIO_CHECK_CMD-/usr/bin/fiocheck}"
FIO_PUSH_CMD="${FIO_PUSH_CMD-/usr/bin/fiopush}"
OSTREE_API_VERSION="${OSTREE_API_VERSION-v2}"
DEV_MODE="${DEV_MODE-0}"

GARAGE_CUSTOMIZE_TARGET_PARAMS='${MACHINE} ${IMAGE_BASENAME} ${TARGET_ARCH}'

if [ "$ENABLE_PTEST" = "1" ] ; then
    OSTREE_BRANCHNAME="${OSTREE_BRANCHNAME}-ptest"
fi

if [ -f "/secrets/targets.sec" ] ; then
	status "Generating credentials.zip"
	dynamic=$(mktemp --suffix=.zip)
	$HERE/../create-creds $dynamic
	SOTA_PACKED_CREDENTIALS=$dynamic
fi

source setup-environment build

if [ "$DEV_MODE" == "1" ]; then
	cat << EOFEOF >> conf/local.conf
DEV_MODE = "1"
EOFEOF
fi

CONF_VERSION=$(grep  ^CONF_VERSION conf/local.conf | cut -d'"' -f 2)


if [ "$CONF_VERSION" == "1" ]; then
	cat << EOFEOF >> conf/local.conf
ACCEPT_EULA_stm32mp1-disco = "1"
ACCEPT_EULA_stm32mp1-eval = "1"
EOFEOF
else
	cat << EOFEOF >> conf/local.conf
ACCEPT_EULA:stm32mp1-disco = "1"
ACCEPT_EULA:stm32mp1-eval = "1"
EOFEOF
fi

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
GARAGE_CUSTOMIZE_TARGET = "${HERE}/customize-target.sh ${FACTORY} ${OTA_LITE_TAG} ${GARAGE_CUSTOMIZE_TARGET_PARAMS}"
DOCKER_COMPOSE_APP = "${DOCKER_COMPOSE_APP}"
USE_FIOTOOLS = "${USE_FIOTOOLS}"
FIO_CHECK_CMD = "${FIO_CHECK_CMD}"
FIO_PUSH_CMD = "${FIO_PUSH_CMD}"
FIO_CHECK_PUSH = "${FIO_PUSH_CMD}"
OSTREE_API_VERSION = "${OSTREE_API_VERSION}"

# Default SOTA client
SOTA_CLIENT = "${SOTA_CLIENT}"

# git-describe version of LMP
LMP_VERSION = "${LMP_VERSION}"
H_BUILD = "${H_BUILD}"

# Default AKLITE tag
AKLITE_TAG = "${AKLITE_TAG}"

# dockerd params
DOCKER_MAX_CONCURRENT_DOWNLOADS = "${DOCKER_MAX_CONCURRENT_DOWNLOADS}"
DOCKER_MAX_DOWNLOAD_ATTEMPTS = "${DOCKER_MAX_DOWNLOAD_ATTEMPTS}"

# mfgtool params
MFGTOOL_FLASH_IMAGE = "${MFGTOOL_FLASH_IMAGE}"

# Bitbake custom logconfig
BB_LOGCONFIG = "bb_logconfig.json"
EOFEOF

# Configure path for the debug/warning logs
sed -e "s|@@ARCHIVE@@|${archive}|" ${HERE}/bb_logconfig.json > bb_logconfig.json

# Additional packages based on the CI job used
if [ "$CONF_VERSION" == "1" ]; then
	cat << EOFEOF >> conf/local.conf
IMAGE_INSTALL_append = " ${EXTRA_IMAGE_INSTALL}"
EOFEOF
else
	cat << EOFEOF >> conf/local.conf
IMAGE_INSTALL:append = " ${EXTRA_IMAGE_INSTALL}"
EOFEOF
fi

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
# Take a tag from a spec like:
#  https://docs.foundries.io/latest/reference/advanced-tagging.html
# and find the first tag name to produce a senible default
LMP_DEVICE_REGISTER_TAG = "$(echo ${OTA_LITE_TAG} | cut -d: -f1 | cut -d, -f1)"
LMP_DEVICE_FACTORY = "${FACTORY}"
LMP_DEVICE_API = "${LMP_DEVICE_API}"
EOFEOF

if [ -z "$SOTA_PACKED_CREDENTIALS" ] || [ ! -f $SOTA_PACKED_CREDENTIALS ] ; then
	status "SOTA_PACKED_CREDENTIALS not found, disabling OSTree publishing logic"
	cat << EOFEOF >> conf/local.conf
SOTA_PACKED_CREDENTIALS = ""
EOFEOF
fi

if [ "${DISABLE_GPLV3}" = "1" ]; then
	cat << EOFEOF >> conf/local.conf
INHERIT += "image-license-checker lmp-disable-gplv3"
IMAGE_LICENSE_CHECKER_ROOTFS_BLACKLIST = "GPL-3.0 LGPL-3.0 AGPL-3.0"
IMAGE_LICENSE_CHECKER_NON_ROOTFS_BLACKLIST = "GPL-3.0 LGPL-3.0 AGPL-3.0"
EOFEOF
fi

if [ -d $SSTATE_CACHE_MIRROR ]; then
	cat << EOFEOF >> conf/local.conf
SSTATE_MIRRORS = "file://.* file://${SSTATE_CACHE_MIRROR}/PATH"
EOFEOF
fi

# Add build id H_BUILD to output files names
if [ "$CONF_VERSION" == "1" ]; then
	cat << EOFEOF >> conf/local.conf
DISTRO_VERSION_append = "-${H_BUILD}-${LMP_VERSION}"
EOFEOF
else
	cat << EOFEOF >> conf/local.conf
DISTRO_VERSION:append = "-${H_BUILD}-${LMP_VERSION}"
EOFEOF
fi

cat << EOFEOF >> conf/auto.conf
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
