#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params MACHINE IMAGE

OSTREE_BRANCHNAME="${OSTREE_BRANCHNAME-lmp-localdev}"
SOTA_CLIENT="${SOTA_CLIENT-aktualizr}"
AKLITE_TAG="${AKLITE_TAG-promoted}"
H_BUILD="${H_BUILD-lmp-localdev}"
LMP_VERSION=$(git --git-dir=.repo/manifests/.git describe --tags)
FACTORY="${FACTORY-lmp}"
UBOOT_SIGN_ENABLE="${UBOOT_SIGN_ENABLE-0}"

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
GARAGE_CUSTOMIZE_TARGET = "${HERE}/customize-target"

# Default SOTA client
SOTA_CLIENT = "${SOTA_CLIENT}"

# git-describe version of LMP
LMP_VERSION = "${LMP_VERSION}"

# Default AKLITE tag
AKLITE_TAG = "${AKLITE_TAG}"

# Who's factory is this?
FOUNDRIES_FACTORY = "${FACTORY}"

# Additional packages based on the CI job used
IMAGE_INSTALL_append = " ${EXTRA_IMAGE_INSTALL}"
EOFEOF

if [ -n "$OTA_LITE_TAG" ] ; then
	cat << EOFEOF >> conf/local.conf
export OTA_LITE_TAG = "${OTA_LITE_TAG}"
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
