#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params MACHINE IMAGE GIT_SHA

DISTRO="${DISTRO-lmp}"

start_ssh_agent
git_config
load_extra_certs

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


set_base_lmp_version

mkdir build conf
cache="/var/cache/bitbake/v${LMP_VERSION_CACHE}-downloads"
if [ -d /var/cache/bitbake/downloads ] ; then
	# TODO remove once we've migrated everyone
	status Migrating to new downloads cache layout
	mv /var/cache/bitbake/downloads $cache
fi
[ -d $cache ] || (mkdir -p $cache; chown builder $cache)
ln -s $cache downloads

chown -R builder .

export FACTORY_SSTATE_CACHE_MIRROR="/var/cache/bitbake/v${LMP_VERSION_CACHE}-sstate-cache"
[ -d $FACTORY_SSTATE_CACHE_MIRROR ] || (mkdir $FACTORY_SSTATE_CACHE_MIRROR && chown builder $FACTORY_SSTATE_CACHE_MIRROR)
su builder -c $HERE/bb-config.sh
touch ${archive}/customize-target.log && chown builder ${archive}/customize-target.log
touch ${archive}/bitbake_buildchart.svg && chown builder ${archive}/bitbake_buildchart.svg
touch ${archive}/bitbake_debug.log \
	${archive}/bitbake_warning.log \
	${archive}/bitbake_cookerdaemon.log \
	${archive}/bitbake_buildstats.log \
	${archive}/bitbake_sstatemirror.log \
	&& chown builder ${archive}/bitbake_*.log
touch ${archive}/bitbake_global_env.txt ${archive}/bitbake_image_env.txt && chown builder ${archive}/bitbake_*_env.txt
touch ${archive}/app-preload.log && chown builder ${archive}/app-preload.log
touch ${archive}/tuf-root-fetch.log && chown builder ${archive}/tuf-root-fetch.log
if [ -n "$OS_SELFTEST" ]; then
	mkdir ${archive}/selftest && chown builder ${archive}/selftest
	su builder -c $HERE/bb-selftest.sh
	exit
fi
su builder -c $HERE/bb-build.sh

status "Post-build processing"

DEPLOY_DIR="$(grep "^DEPLOY_DIR=" ${archive}/bitbake_global_env.txt | cut -d'=' -f2 | tr -d '"')"
DEPLOY_DIR_IMAGE="${DEPLOY_DIR}/images/${MACHINE}"
DEPLOY_DIR_SDK="${DEPLOY_DIR}/sdk/"

# Prepare files to publish
rm -f ${DEPLOY_DIR_IMAGE}/*.txt
## Only publish wic.gz
rm -f ${DEPLOY_DIR_IMAGE}/*.wic

# Link the license manifest for all the images produced by the build
for img in ${DEPLOY_DIR_IMAGE}/*${MACHINE}.manifest; do
	image_name=`basename ${img} | sed -e "s/.manifest//"`
	image_name_id=`readlink ${img} | sed -e "s/\..*manifest//"`
	if [ -f ${DEPLOY_DIR}/licenses/${image_name_id}/license.manifest ]; then
		cp ${DEPLOY_DIR}/licenses/${image_name_id}/license.manifest ${DEPLOY_DIR_IMAGE}/${image_name_id}.license.manifest
		ln -sf ${image_name_id}.license.manifest ${DEPLOY_DIR_IMAGE}/${image_name}.license.manifest
	fi
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
	mkdir ${archive}/sdk

	# Bitbake env output
	gzip -f ${archive}/bitbake_global_env.txt
	gzip -f ${archive}/bitbake_image_env.txt
	mv ${archive}/bitbake_*_env.txt.gz ${archive}/other/

	# Compress and publish bitbake's debug build output
	gzip -f ${archive}/bitbake_debug.log
	mv ${archive}/bitbake_debug.log.gz ${archive}/other/
	mv ${archive}/bitbake_warning.log ${archive}/other/
	mv ${archive}/bitbake_cookerdaemon.log ${archive}/other/
	mv ${archive}/bitbake_buildstats.log ${archive}/other/
	mv ${archive}/bitbake_buildchart.svg ${archive}/other/
	gzip -f ${archive}/bitbake_sstatemirror.log
	mv ${archive}/bitbake_sstatemirror.log.gz ${archive}/other/

	# Compress and publish source tarball (for *GPL* packages)
	if [ -d ${DEPLOY_DIR_IMAGE}/source-release ]; then
		tar --remove-files -C ${DEPLOY_DIR_IMAGE} -cf ${MACHINE}-source-release.tar source-release
		mv ${MACHINE}-source-release.tar ${archive}/other/
	fi

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
	cp ${DEPLOY_DIR_IMAGE}/QEMU*.fd ${archive}/other/ || true
	cp ${DEPLOY_DIR_IMAGE}/SBSA_FLASH*.fd ${archive}/other/ || true
	# Copy the bootloader used by RISC-V targets
	cp ${DEPLOY_DIR_IMAGE}/bbl* ${archive}/other/ || true
	cp ${DEPLOY_DIR_IMAGE}/fw_* ${archive}/other/ || true
	# Copy the ARM firmware binaries
	cp ${DEPLOY_DIR_IMAGE}/se_*.bin ${archive}/other/ || true
	cp ${DEPLOY_DIR_IMAGE}/es_*.bin ${archive}/other/ || true
	cp ${DEPLOY_DIR_IMAGE}/*-board-firmware*.tar.gz ${archive}/other/ || true
	# Additional firmware files
	cp ${DEPLOY_DIR_IMAGE}/bl*.img ${archive}/other/ || true
	cp ${DEPLOY_DIR_IMAGE}/fip.bin ${archive}/other/ || true
	cp ${DEPLOY_DIR_IMAGE}/lk.bin ${archive}/other/ || true
	# BSP specific files
	cp ${DEPLOY_DIR_IMAGE}/rity.json ${archive}/other/ || true
	# Copy boot.cmd and boot.itb (signed boot script) if available
	cp ${DEPLOY_DIR_IMAGE}/boot.cmd ${archive}/other/ || true
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
			cp ${DEPLOY_DIR_IMAGE}/${extra_file} ${archive}/ || true
		done
	fi
	## Copy the SDK installation file
	cp ${DEPLOY_DIR_SDK}/lmp*.sh ${archive}/sdk/ || true

	# Remove ota-ext4 in case the compressed format is available (to reduce time spent uploading)
	if [ -f ${archive}/other/${IMAGE}-${MACHINE}.ota-ext4.gz ]; then
		rm -f ${archive}/other/${IMAGE}-${MACHINE}.ota-ext4
	fi

	# Make the main img.gz and respective bmap file be in the root of the archive
	mv ${archive}/other/lmp-*.wic.gz ${archive}/ || true
	mv ${archive}/other/lmp-*.wic.bmap ${archive}/ || true
	# NVIDIA targets use a tegraflash tarball
	mv ${archive}/other/lmp-*.tegraflash.tar.gz ${archive}/ || true
	# Telechips targets use a fai image
	mv ${archive}/other/lmp-*.fai ${archive}/ || true
	# Mediatek targets use aiotflash images
	mv ${archive}/other/lmp-*.aiotflash.tar ${archive}/ || true

	# Move bootloader / boot firmware to the root of the archive
	## Intel (used by Qemu)
	mv ${archive}/other/ovmf.qcow2 ${archive}/ || true
	mv ${archive}/other/ovmf.secboot.qcow2 ${archive}/ || true
	## QEMU Generic ARM64
	mv ${archive}/other/QEMU*.fd ${archive}/ || true
	mv ${archive}/other/SBSA_FLASH*.fd ${archive}/ || true
	## Only move files consumed by iMX if not mfgtool to avoid confusion
	if [ "${DISTRO}" != "lmp-mfgtool" ]; then
		## Targets with SPL / u-boot.itb
		mv ${archive}/other/SPL-${MACHINE} ${archive}/ || true
		mv ${archive}/other/u-boot-${MACHINE}.itb ${archive}/ || true
		mv ${archive}/other/u-boot-${MACHINE}.rom ${archive}/ || true
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
	## Telechips boot-firmware
	mv ${archive}/other/boot-firmware-*.tar.gz ${archive}/ || true

	# Create MD5SUMS file
	find ${archive} -type f | sort | xargs md5sum > MD5SUMS.txt
	sed -i "s|${archive}/||" MD5SUMS.txt
	mv MD5SUMS.txt ${archive}/other/

	mv ${archive}/manifest* ${archive}/other/
	cp "${DEPLOY_DIR_IMAGE}/os-release" "${archive}/" || true

	mkdir ${archive}/sboms
	mv ${archive}/other/*spdx* ${archive}/sboms/ || true
fi
