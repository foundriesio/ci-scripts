#!/bin/bash -E

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params MACHINE

export JOB_NAME="fio-jobserv ${H_PROJECT}/${H_BUILD}/${H_RUN}"

if [ "$MACHINE" = "beaglebone-yocto" ] ; then
	DTB_URL="$(generate-public-url ${H_TRIGGER_URL}/other/am335x-boneblack-wireless.dtb)"
	DEVICE_TYPE="beaglebone-black"
	PROMPT="beaglebone-yocto:"
fi

if [ "$MACHINE" = "cl-som-imx7" ] ; then
	DTB_URL="$(generate-public-url ${H_TRIGGER_URL}/other/imx7d-sbc-iot-imx7.dtb)"
	DEVICE_TYPE="imx7d-sbc-iot-imx7"
	PROMPT="cl-som-imx7:"
fi

ARM_RAMDISK="http://storage.kernelci.org/images/rootfs/buildroot/armel/rootfs.cpio.gz"
DEPLOY_DEVICE="mmc"
IMAGE_URL="$(generate-public-url ${H_TRIGGER_URL}/lmp-gateway-image-${MACHINE}.img.gz)"
KERNEL_TYPE="zimage"
KERNEL_URL="$(generate-public-url ${H_TRIGGER_URL}/other/zImage)"
MODULES_URL="$(generate-public-url ${H_TRIGGER_URL}/other/modules-${MACHINE}.tgz)"
ROOTFS_COMP="gz"

cat >/archive/lmp-${MACHINE}.yml <<EOF
job_name: '${JOB_NAME}'
device_type: '${DEVICE_TYPE}'
timeouts:
  job:
    minutes: 45
priority: medium
visibility: public

actions:
- deploy:
    namespace: osf-deploy
    timeout:
      minutes: 2
    to: tftp
    kernel:
      url: '${KERNEL_URL}'
      type: '${KERNEL_TYPE}'
    ramdisk:
      url: '${ARM_RAMDISK}'
      compression: gz
    modules:
      url: '${MODULES_URL}'
      compression: gz
    dtb:
      url: '${DTB_URL}'
    os: oe

- boot:
    method: u-boot
    namespace: osf-deploy
    commands: ramdisk
    type: '${KERNEL_TYPE}'
    prompts:
      - '/ #'

- deploy:
    os: oe
    namespace: osf-deploy
    timeout:
      minutes: 25
    to: sd
    image:
      url: '${IMAGE_URL}'
      compression: '${ROOTFS_COMP}'
    device: '${DEPLOY_DEVICE}'
    download:
      tool: /usr/bin/wget
      prompt: Connecting to
      options: --no-check-certificate -O - {DOWNLOAD_URL}

- deploy:
    os: oe
    namespace: osf-test
    timeout:
      minutes: 1
    to: dummy

- boot:
    method: dummy
    namespace: osf-test
    connection-namespace: osf-deploy
    timeout:
      minutes: 55
    auto_login:
      login_prompt: 'login:'
      username: "osf"
      password_prompt: "Password:"
      password: "osf"
      login_commands:
        - echo osf | sudo -S su
        - sudo su
        - whoami
        - ls /
    prompts:
      - '${PROMPT}'
EOF

lava-submit /archive/lmp-${MACHINE}.yml
