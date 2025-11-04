#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params MACHINE IMAGE OTA_LITE_TAG

OSTREE_BRANCHNAME="${OSTREE_BRANCHNAME-lmp-localdev}"
SOTA_CLIENT="${SOTA_CLIENT-aktualizr}"
AKLITE_TAG="${AKLITE_TAG-promoted}"
H_BUILD="${H_BUILD-lmp-localdev}"
LMP_VERSION="${LMP_VERSION-unknown}"
FACTORY="${FACTORY-lmp}"
LMP_DEVICE_API="${LMP_DEVICE_API-https://api.${dns_base}/ota/devices/}"
LMP_OAUTH_API="${LMP_OAUTH_API-https://app.${dns_base}/oauth}"
FIO_HUB_URL="${FIO_HUB_URL-${hub_fio}}"
DISABLE_GPLV3="${DISABLE_GPLV3-0}"
DOCKER_MAX_CONCURRENT_DOWNLOADS="${DOCKER_MAX_CONCURRENT_DOWNLOADS-3}"
DOCKER_MAX_DOWNLOAD_ATTEMPTS="${DOCKER_MAX_DOWNLOAD_ATTEMPTS-5}"
MFGTOOL_FLASH_IMAGE="${MFGTOOL_FLASH_IMAGE-lmp-factory-image}"
USE_FIOTOOLS="${USE_FIOTOOLS-1}"
FIO_PUSH_BIN="${FIO_PUSH_BIN-/usr/bin/fiopush}"
FIO_CHECK_BIN="${FIO_CHECK_BIN-/usr/bin/fiocheck}"
OSTREE_API_VERSION="${OSTREE_API_VERSION-v2}"
DEV_MODE="${DEV_MODE-0}"
BUILD_SDK="${BUILD_SDK-0}"
LMP_ROLLBACK_PROTECTION_ENABLE="${LMP_ROLLBACK_PROTECTION_ENABLE-0}"
DISABLE_LOGCONFIG="${DISABLE_LOGCONFIG-0}"

GARAGE_CUSTOMIZE_TARGET_PARAMS='${MACHINE} ${IMAGE_BASENAME} ${TARGET_ARCH} ${DISTRO_VERSION}'
TUF_TARGETS_EXPIRE="${TUF_TARGETS_EXPIRE-1Y}"

if [ -f "/secrets/targets.sec" ] ; then
	status "Generating credentials.zip"
	dynamic=$(mktemp --suffix=.zip)
	$HERE/../create-creds $dynamic
	SOTA_PACKED_CREDENTIALS=$dynamic
fi

# EULA handling (assume accepted as we now have a click through process when creating the factory)
EULA_stm32mp1disco="1"
EULA_stm32mp15disco="1"
EULA_stm32mp1eval="1"
EULA_stm32mp15eval="1"

# meta-lmp requires this value to be a script and not a script with arguments.
# This creates a wrapper that handles the arguments
fetch_creds="${PWD}/fetch-root-meta-ci-helper.sh"
cat << EOFEOF > ${fetch_creds}
#!/bin/sh -e
H_RUN_URL=${H_RUN_URL} ${HERE}/fetch-root-meta.sh
EOFEOF
chmod +x ${fetch_creds}

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
ACCEPT_EULA:stm32mp15-disco = "1"
ACCEPT_EULA:stm32mp15-eval = "1"
LICENSE_FLAGS_ACCEPTED:append:rpi = " synaptics-killswitch"
EOFEOF
fi

cat << EOFEOF >> conf/local.conf
CONNECTIVITY_CHECK_URIS = "https://www.google.com/"

ACCEPT_FSL_EULA = "1"

BB_GENERATE_MIRROR_TARBALLS = "1"

# Factory name
LMP_FACTORY = "${FACTORY}"
LMP_FACTORY_IMAGE = "${IMAGE}"

# SOTA params
SOTA_PACKED_CREDENTIALS = "${SOTA_PACKED_CREDENTIALS}"
OSTREE_BRANCHNAME = "\${MACHINE}-${OSTREE_BRANCHNAME}"
GARAGE_TARGET_VERSION = "\${H_BUILD}"
GARAGE_TARGET_EXPIRE_AFTER = "${TUF_TARGETS_EXPIRE}"
GARAGE_TARGET_URL = "https://ci.${dns_base}/projects/${H_PROJECT}/builds/\${H_BUILD}"
GARAGE_CUSTOMIZE_TARGET = "${HERE}/customize-target.sh ${H_RUN_URL} ${FACTORY} ${OTA_LITE_TAG} ${GARAGE_CUSTOMIZE_TARGET_PARAMS}"
GARAGE_PUSH_RETRIES = "${GARAGE_PUSH_RETRIES-5}"
GARAGE_PUSH_RETRIES_SLEEP = "${GARAGE_PUSH_RETRIES_SLEEP-10}"
DOCKER_COMPOSE_APP = "${DOCKER_COMPOSE_APP}"
USE_FIOTOOLS = "${USE_FIOTOOLS}"
FIO_CHECK_BIN = "${FIO_CHECK_BIN}"
FIO_PUSH_BIN = "${FIO_PUSH_BIN}"
FIO_CHECK_CMD = "${HERE}/fiocheck.sh"
FIO_PUSH_CMD = "${HERE}/fiopush.sh"
FIO_CHECK_PUSH = "${HERE}/fiopush.sh"
OSTREE_API_VERSION = "${OSTREE_API_VERSION}"

# Apps preloading params
APP_PRELOAD_WITHIN_OE_BUILD = "${APP_PRELOAD_WITHIN_OE_BUILD}"
APP_PRELOADER = "${HERE}/../preload-apps.sh"
APP_SHORTLIST = "${APP_SHORTLIST}"
APP_PRELOAD_TOKEN_FILE = "/secrets/osftok"
APP_PRELOAD_REGISTRY_SECRETS_FILE = "/secrets/container-registries"
APP_PRELOAD_LOG_FILE = "/archive/app-preload.log"
COMPOSE_APP_TYPE = "${COMPOSE_APP_TYPE-restorable}"

# TUF root meta provisioning parameters
SOTA_TUF_ROOT_PROVISION = "${SOTA_TUF_ROOT_PROVISION-1}"
SOTA_TUF_ROOT_FETCHER = "${fetch_creds}"
SOTA_TUF_ROOT_DIR = "usr/lib/sota/tuf"
SOTA_TUF_ROOT_LOG_FILE = "/archive/tuf-root-fetch.log"

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
EOFEOF

if [ "${DISABLE_LOGCONFIG}" != "1" ]; then
	cat << EOFEOF >> conf/local.conf

# Bitbake custom logconfig
BB_LOGCONFIG = "${PWD}/bb_logconfig.json"
EOFEOF
fi

# Configure path for the debug/warning logs
sed -e "s|@@ARCHIVE@@|${archive}|" ${HERE}/bb_logconfig.json > bb_logconfig.json

# Additional packages based on the CI job used
if [ -n "${EXTRA_IMAGE_INSTALL}" ]; then
	if [ "$CONF_VERSION" == "1" ]; then
		cat << EOFEOF >> conf/local.conf
IMAGE_INSTALL_append = " ${EXTRA_IMAGE_INSTALL}"
EOFEOF
	else
		cat << EOFEOF >> conf/local.conf
IMAGE_INSTALL:append = " ${EXTRA_IMAGE_INSTALL}"
EOFEOF
	fi
fi

cat << EOFEOF >> conf/local.conf
# Take a tag from a spec like:
#  https://docs.foundries.io/latest/reference-manual/ota/advanced-tagging.html
# and find the first tag name to produce a sensible default
LMP_DEVICE_REGISTER_TAG = "$(echo ${OTA_LITE_TAG} | cut -d: -f1 | cut -d, -f1)"
LMP_DEVICE_FACTORY = "${FACTORY}"
LMP_DEVICE_API = "${LMP_DEVICE_API}"
LMP_OAUTH_API = "${LMP_OAUTH_API}"
FIO_HUB_URL = "${FIO_HUB_URL}"
EOFEOF

if [ -z "$SOTA_PACKED_CREDENTIALS" ] || [ ! -f $SOTA_PACKED_CREDENTIALS ] ; then
	status "SOTA_PACKED_CREDENTIALS not found, disabling OSTree publishing logic"
	cat << EOFEOF >> conf/local.conf
SOTA_PACKED_CREDENTIALS = ""
EOFEOF
fi

if [ "${LMP_ROLLBACK_PROTECTION_ENABLE}" = "1" ]; then
	status "Configuring boot firmware rollback protection, LMP_ROLLBACK_PROTECTION_ENABLE = ${LMP_ROLLBACK_PROTECTION_ENABLE}"
	cat << EOFEOF >> conf/local.conf
LMP_ROLLBACK_PROTECTION_ENABLE = "${LMP_ROLLBACK_PROTECTION_ENABLE}"
EOFEOF
fi

if [ "${DISABLE_GPLV3}" = "1" ]; then
	if [ -f ../layers/meta-lmp-base/classes/lmp-no-gplv3.bbclass ]; then
		cat << EOFEOF >> conf/local.conf
INHERIT += "lmp-no-gplv3"
EOFEOF
	else
		cat << EOFEOF >> conf/local.conf
INHERIT += "image-license-checker lmp-disable-gplv3"
IMAGE_LICENSE_CHECKER_ROOTFS_BLACKLIST = "GPL-3.0 LGPL-3.0 AGPL-3.0"
IMAGE_LICENSE_CHECKER_NON_ROOTFS_BLACKLIST = "GPL-3.0 LGPL-3.0 AGPL-3.0"
IMAGE_LICENSE_CHECKER_ROOTFS_DENYLIST = "GPL-3.0-only GPL-3.0-or-later LGPL-3.0* AGPL-3.0*"
IMAGE_LICENSE_CHECKER_NON_ROOTFS_DENYLIST = "GPL-3.0-only GPL-3.0-or-later LGPL-3.0* AGPL-3.0*"
EOFEOF
	fi
fi

sstate_mirror="https://storage.googleapis.com/lmp-cache/v${LMP_VERSION_CACHE}-sstate-cache"
if [[ "${FORKED_FROM}" != "lmp" ]] ; then
	sstate_mirror="https://storage.googleapis.com/lmp-cache/${FORKED_FROM}/v${LMP_VERSION_CACHE}-sstate-cache"
fi
	cat << EOFEOF >> conf/local.conf

# prioritize local nfs factory mirror over public https lmp
SSTATE_MIRRORS ?= " \\
	file://.* file://${FACTORY_SSTATE_CACHE_MIRROR}/PATH \\
	file://.* ${sstate_mirror}/PATH \\
"
EOFEOF

# Add build id H_BUILD to output files names
cat << 'EOFEOF' >> conf/local.conf
DISTRO_VERSION_EXTENDED ?= "-${H_BUILD}-${LMP_VERSION}"
EOFEOF
if [ "$CONF_VERSION" == "1" ]; then
	cat << 'EOFEOF' >> conf/local.conf
DISTRO_VERSION_append = "${DISTRO_VERSION_EXTENDED}"
EOFEOF
else
	cat << 'EOFEOF' >> conf/local.conf
DISTRO_VERSION:append = "${DISTRO_VERSION_EXTENDED}"
EOFEOF
fi

cat << EOFEOF >> conf/auto.conf

# archive sources for target recipes (for license compliance)
INHERIT += "archiver"
COPYLEFT_RECIPE_TYPES = "target"
ARCHIVER_MODE[src] = "original"
ARCHIVER_MODE[diff] = "1"
EOFEOF

# spdx is support since kirkstone so check if this oe-core have support
if [ -f ../layers/openembedded-core/meta/classes/create-spdx.bbclass ]; then
	cat << EOFEOF >> conf/auto.conf

# create SPDX (SBOM) documents
INHERIT += "create-spdx"
EOFEOF
fi

for x in $(ls conf/*.conf) ; do
	status "$x"
	cat $x | indent
done
