#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params MACHINE IMAGE GIT_SHA

DISTRO="${DISTRO-lmp}"

manifest="file://$(pwd)/.git -b $GIT_SHA"
# repo init won't work off detached heads, so do this to work around:
git branch pr-branch $GIT_SHA
mkdir /srv/oe
cd /srv/oe
repo_sync $manifest


mkdir build conf
cache="/var/cache/bitbake/downloads"
[ -d $cache ] || (mkdir $cache; chown builder $cache)
ln -s $cache downloads

cache="/var/cache/bitbake/sstate-cache-${DISTRO}"
[ -d $cache ] || (mkdir $cache; chown builder $cache)
ln -s $cache sstate-cache

export EULA_stih410b2260=1

chown -R builder .

su builder -c $HERE/bb-config.sh
su builder -c $HERE/bb-build.sh

DEPLOY_DIR_IMAGE=$(cat build/image_dir)

# Prepare files to publish
rm -f ${DEPLOY_DIR_IMAGE}/*.txt

# FIXME: Sparse images here, until it gets done by OE
case "${MACHINE}" in
	hikey|hikey960|dragonboard-410c|dragonboard-820c)
		otaimg=${DEPLOY_DIR_IMAGE}/$(readlink ${DEPLOY_DIR_IMAGE}/${IMAGE}-${MACHINE}.ota-ext4)
		ext2simg -v ${otaimg} ${otaimg}.img
		gzip -9 ${otaimg}.img
		ln -s $(basename ${otaimg}.img.gz) ${DEPLOY_DIR_IMAGE}/${IMAGE}-${MACHINE}.ota-ext4.img.gz
	;;
esac

# Also create "img" images as they are compatible with standard flashing tools
for img in ${DEPLOY_DIR_IMAGE}/*${MACHINE}.wic.gz; do
	ln -s $(basename ${img}) ${img%.wic.gz}.img.gz
done

if [ -d "${archive}" ] ; then
	mkdir ${archive}/other

	# Compress and publish the ostree repository
	if [ -d ${DEPLOY_DIR_IMAGE}/ostree_repo ]; then
		cat ${DEPLOY_DIR_IMAGE}/ostree_repo/refs/heads/${MACHINE}-${OSTREE_BRANCHNAME} > ${archive}/other/ostree.sha.txt
		tar --remove-files -C ${DEPLOY_DIR_IMAGE} -cjf ${MACHINE}-ostree_repo.tar.bz2 ostree_repo
		mv ${MACHINE}-ostree_repo.tar.bz2 ${archive}/other/
	fi

	# Copy files based on the links created as they are named without timestamp
	find ${DEPLOY_DIR_IMAGE} -maxdepth 1 -type l -exec cp -L '{}' ${archive}/other/ \;
	# Copy extra folders if available (e.g. bootloader)
	find ${DEPLOY_DIR_IMAGE}/* -maxdepth 0 -type d -exec cp -r '{}' ${archive}/other/ \;
	# Copy the ovmf firmware files used by virtual machines
	cp ${DEPLOY_DIR_IMAGE}/ovmf.* ${archive}/other/ || true
	# Copy the bootloader used by RISC-V targets
	cp ${DEPLOY_DIR_IMAGE}/bbl* ${archive}/other/ || true

	# Make the main img.gz be in the root of the archive
	mv ${archive}/other/lmp-*.img.gz ${archive}/ || true
	mv ${archive}/other/boot*.img ${archive}/ || true

	# Create MD5SUMS file
	find ${archive} -type f | sort | xargs md5sum > MD5SUMS.txt
	sed -i "s|${archive}/||" MD5SUMS.txt
	mv MD5SUMS.txt ${archive}/other/

	mv ${archive}/manifest* ${archive}/other/
fi
