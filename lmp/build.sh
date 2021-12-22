#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params MACHINE IMAGE GIT_SHA

DISTRO="${DISTRO-lmp}"

if [[ $GIT_URL == *"/lmp-manifest.git"* ]]; then
	status "Build triggered by change to lmp-manifest"
	manifest="file://$(pwd)/.git -b $GIT_SHA"
	# repo init won't work off detached heads, so do this to work around:
	git branch pr-branch $GIT_SHA
	# Check to make sure REPO_INIT_OVERRIDES isn't setting a "-b <ref>".
	# That will break our logic for checking out the exact GIT_SHA above
	export REPO_INIT_OVERRIDES=$(echo $REPO_INIT_OVERRIDES | sed -e 's/-b\s*\S*//')
	mkdir /srv/oe && cd /srv/oe
	repo_sync $manifest
else
	repourl="$(dirname ${GIT_URL})/lmp-manifest.git"
	layer="$(basename ${GIT_URL%.git})"
	status "Build triggered by change to OE layer: $layer"
	status "Will repo sync from $repourl"
	mkdir /srv/oe && cd /srv/oe
	repo_sync $repourl
	run rm -rf layers/$layer
	run ln -s /repo layers/$layer
fi
cat /root/.gitconfig >>  /home/builder/.gitconfig
cp /root/.netrc /home/builder/.netrc || true

mkdir build conf
cache="/var/cache/bitbake/downloads"
[ -d $cache ] || (mkdir $cache; chown builder $cache)
ln -s $cache downloads

cache="/var/cache/bitbake/sstate-cache-${DISTRO}"
[ -d $cache ] || (mkdir $cache; chown builder $cache)
ln -s $cache sstate-cache

chown -R builder .

su builder -c $HERE/bb-config.sh
touch ${archive}/customize-target.log && chown builder ${archive}/customize-target.log
# It has to be inline with definition of APP_IMAGES_PRELOAD_LOG_FILE in bb-config.sh
touch "${archive}/app-images-preload.log" && chown builder "${archive}/app-images-preload.log"
touch "${archive}/os-release" && chown builder "${archive}/os-release"
su builder -c $HERE/bb-build.sh

DEPLOY_DIR="$(cat build/deploy_dir)"
DEPLOY_DIR_IMAGE="${DEPLOY_DIR}/images/${MACHINE}"

# Prepare files to publish
rm -f ${DEPLOY_DIR_IMAGE}/*.txt
## Only publish wic.gz
rm -f ${DEPLOY_DIR_IMAGE}/*.wic

# Link the license manifest for all the images produced by the build
for img in ${DEPLOY_DIR_IMAGE}/*${MACHINE}.manifest; do
	image_name=`basename ${img} | sed -e "s/.manifest//"`
	image_name_id=`readlink ${img} | sed -e "s/\..*manifest//"`
	cp ${DEPLOY_DIR}/licenses/${image_name_id}/license.manifest ${DEPLOY_DIR_IMAGE}/${image_name_id}.license.manifest
	ln -sf ${image_name_id}.license.manifest ${DEPLOY_DIR_IMAGE}/${image_name}.license.manifest
	# Also take care of the image_license, which contains the binaries used by wic outside the rootfs
	if [ -f ${DEPLOY_DIR}/licenses/${image_name_id}/image_license.manifest ]; then
		cp ${DEPLOY_DIR}/licenses/${image_name_id}/image_license.manifest ${DEPLOY_DIR_IMAGE}/${image_name_id}.image_license.manifest
		ln -sf ${image_name_id}.image_license.manifest ${DEPLOY_DIR_IMAGE}/${image_name}.image_license.manifest
	fi
done

# Generate a tarball containing the source code of *GPL* packages (based on yocto dev-manual)
DEPLOY_SOURCES="${DEPLOY_DIR_IMAGE}/source-release"
if [ -d ${DEPLOY_DIR}/sources ]; then
	mkdir -p ${DEPLOY_SOURCES}
	for sarch in ${DEPLOY_DIR}/sources/*; do
		for pkg in ${sarch}/*; do
			# Get package name from path
			p=`basename $pkg`
			p=${p%-*}
			p=${p%-*}

			# Check if package is part of any of the produced images
			grep -q "NAME: ${p}$" ${DEPLOY_DIR_IMAGE}/*.manifest || continue

			# Only archive GPL packages (update *GPL* regex for additional licenses)
			numfiles=`ls ${DEPLOY_DIR}/licenses/${p}/*GPL* 2> /dev/null | wc -l`
			if [ ${numfiles} -gt 0 ]; then
				mkdir -p ${DEPLOY_SOURCES}/${p}/source
				cp -f ${pkg}/* ${DEPLOY_SOURCES}/${p}/source 2> /dev/null
				mkdir -p ${DEPLOY_SOURCES}/${p}/license
				cp -f ${DEPLOY_DIR}/licenses/${p}/* ${DEPLOY_SOURCES}/${p}/license 2> /dev/null
			fi
		done
	done
fi

if [ -d "${archive}" ] ; then
	mkdir ${archive}/other

	# Compress and publish bitbake's debug build output
	if [ -f build/bitbake_debug.log ]; then
		gzip -f build/bitbake_debug.log
		mv build/bitbake_debug.log.gz ${archive}/other/
		mv build/bitbake_warning.log ${archive}/other/
	fi

	# Compress and publish source tarball (for *GPL* packages)
	if [ -d ${DEPLOY_DIR_IMAGE}/source-release ]; then
		tar --remove-files -C ${DEPLOY_DIR_IMAGE} -cf ${MACHINE}-source-release.tar source-release
		mv ${MACHINE}-source-release.tar ${archive}/other/
	fi

	# Compress and publish the ostree repository
	if [ -d ${DEPLOY_DIR_IMAGE}/ostree_repo ]; then
		# Update branchname in case ptest is enabled as done by bb-config.sh
		if [ "$ENABLE_PTEST" = "1" ] ; then
			OSTREE_BRANCHNAME="${OSTREE_BRANCHNAME}-ptest"
		fi
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
	cp ${DEPLOY_DIR_IMAGE}/fw_* ${archive}/other/ || true
	# Copy the ARM firmware binaries
	cp ${DEPLOY_DIR_IMAGE}/se_*.bin ${archive}/other/ || true
	cp ${DEPLOY_DIR_IMAGE}/es_*.bin ${archive}/other/ || true
	cp ${DEPLOY_DIR_IMAGE}/*-board-firmware*.tar.gz ${archive}/other/ || true
	# Copy boot.itb (signed boot script) if available
	cp ${DEPLOY_DIR_IMAGE}/boot.itb ${archive}/other/ || true
	# Flash layout for STM32 devices
	cp ${DEPLOY_DIR_IMAGE}/flashlayouts*.tar.gz ${archive}/other/ || true

	## Targets that support iMX redundant boot
	cp ${DEPLOY_DIR_IMAGE}/sit-${MACHINE}.bin ${archive}/other/ || true

	# mfgtool-files (iMX targets)
	if [ "${DISTRO}" = "lmp-mfgtool" ]; then
		cp ${DEPLOY_DIR_IMAGE}/mfgtool-files-${MACHINE}.tar.gz ${archive}/ || true
	fi
	# Handle user provided extra artifacts
	if [ ! -z "${EXTRA_ARTIFACTS}" ]; then
		for extra_file in ${EXTRA_ARTIFACTS}; do
			cp ${DEPLOY_DIR_IMAGE}/${extra_file} ${archive}/
		done
	fi

	# Make the main img.gz be in the root of the archive
	mv ${archive}/other/lmp-*.wic.gz ${archive}/ || true
	# NVIDIA targets use a tegraflash tarball
	mv ${archive}/other/lmp-*.tegraflash.tar.gz ${archive}/ || true

	# Move bootloader / boot firmware to the root of the archive
	## Intel (used by Qemu)
	mv ${archive}/other/ovmf.qcow2 ${archive}/ || true
	mv ${archive}/other/ovmf.secboot.qcow2 ${archive}/ || true
	## Only move files consumed by iMX if not mfgtool to avoid confusion
	if [ "${DISTRO}" != "lmp-mfgtool" ]; then
		## Targets with SPL / u-boot.itb
		mv ${archive}/other/SPL-${MACHINE} ${archive}/ || true
		mv ${archive}/other/u-boot-${MACHINE}.itb ${archive}/ || true
		## iMX targets with imx-boot
		mv ${archive}/other/imx-boot ${archive}/ || true
		mv ${archive}/other/imx-boot-${MACHINE}* ${archive}/ || true
		## HDMI firmware for iMX8MQ
		mv ${archive}/other/imx-boot-tools/signed_hdmi_imx8m.bin ${archive}/ || true
		## Targets that support iMX redundant boot
		mv ${archive}/other/sit-${MACHINE}.bin ${archive}/ || true
	fi
	## ARM custom targets
	mv ${archive}/other/se_romfw.bin ${archive}/ || true
	mv ${archive}/other/es_flashfw.bin ${archive}/ || true
	mv ${archive}/other/bl1.bin ${archive}/ || true
	mv ${archive}/other/flash.bin ${archive}/ || true
	## RISC-V (used by Qemu)
	mv ${archive}/other/fw_payload.elf ${archive}/ || true

	# Create MD5SUMS file
	find ${archive} -type f | sort | xargs md5sum > MD5SUMS.txt
	sed -i "s|${archive}/||" MD5SUMS.txt
	mv MD5SUMS.txt ${archive}/other/

	mv ${archive}/manifest* ${archive}/other/
fi
