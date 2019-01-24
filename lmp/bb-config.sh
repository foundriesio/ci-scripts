#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params MACHINE IMAGE

OSTREE_BRANCHNAME="${OSTREE_BRANCHNAME-lmp-localdev}"
H_BUILD="${H_BUILD-lmp-localdev}"

source setup-environment build

cat << EOFEOF >> conf/local.conf
ACCEPT_FSL_EULA = "1"
BB_GENERATE_MIRROR_TARBALLS = "1"

# SOTA params
SOTA_PACKED_CREDENTIALS = ""
OSTREE_BRANCHNAME = "${MACHINE}-${OSTREE_BRANCHNAME}"
GARAGE_SIGN_REPO = "/tmp/garage_sign_repo"
GARAGE_TARGET_VERSION = "${H_BUILD}"
GARAGE_TARGET_URL = "https://foundries.io/b/development/lmp/${H_BUILD}/"
EOFEOF

if [ -n "$SOTA_PACKED_CREDENTIALS" ] && [ -f $SOTA_PACKED_CREDENTIALS ] ; then
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
DISTRO_VERSION_append = "-${H_BUILD}"

# get build stats to make sure that we use sstate properly
INHERIT += "buildstats buildstats-summary"
EOFEOF

if [ $(ls ../sstate-cache | wc -l) -ne 0 ] ; then
	status "Found existing sstate cache, using local copy"
	echo 'SSTATE_MIRRORS = ""' >> conf/auto.conf
fi

for x in $(ls conf/*.conf) ; do
	status "$x"
	cat $x | indent
done
