#!/bin/sh

set -euo pipefail

HERE=$(dirname $(readlink -f $0))
source ${HERE}/../helpers.sh

tmpdir=$(mktemp -d)
trap "echo removing tmpdir; rm -rf $tmpdir" TERM INT EXIT

cd $tmpdir
mkdir .repo

# Create a fake customer lmp-manifest
run git clone https://github.com/foundriesio/lmp-manifest fake
# Move to a commit after 88 and before 89
run git --git-dir fake/.git tag v123 d0bf3844aabce3028969fda2c3fd3f443ae3b4f7
run git --git-dir fake/.git reset --hard d0bf3844aabce3028969fda2c3fd3f443ae3b4f7

run git clone fake .repo/manifests
mv .repo/manifests/.git .repo/manifests.git

export H_PROJECT="andy-corp/lmp"
set_base_lmp_version
if [[ "$LMP_VER" != "88" ]] ; then
	echo "ERROR: LMP_VER != 88 - ${LMP_VER}"
	exit 1
fi

latest=$(git --git-dir .repo/manifests.git describe --tag)
if [[ "$latest" != "v123" ]] ; then
	echo "ERROR: latest tag != v123 - $latest"
	exit 1
fi

run git --git-dir .repo/manifests.git remote remove upstream
export H_PROJECT="lmp"
set_base_lmp_version
if [[ "$LMP_VER" != "89" ]] ; then
	echo "ERROR: LMP_VER != 89 - ${LMP_VER}"
	exit 1
fi
