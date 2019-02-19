#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params PLATFORM

cd /srv
west || run pip3 install -U west
run west init -m https://github.com/foundriesio/zmp-manifest --mr refs/heads/master
run west update
west manifest --freeze --out /archive/west.yml

run pip3 install -r zmp-manifest/requirements.txt

APP="zmp-samples/dm-lwm2m"
status "Overriding the west manifest's $APP with cloned value in /repo"
run rm -rf $APP
run ln -s /repo ./$APP

status "Compiling $APP bootloader"
run west build -s mcuboot/boot/zephyr -d build-mcuboot -b $PLATFORM

status "Compiling $APP application"
if [ $PLATFORM = "frdm_k64f" ]; then
	echo 'CONFIG_NET_DHCPV4=y' >> $APP/boards/frdm_k64f-local.conf
	# 192.168.0.118 = andy's minnowboard
	echo 'CONFIG_NET_CONFIG_PEER_IPV4_ADDR="192.168.0.118"' >> $APP/boards/frdm_k64f-local.conf
	echo 'CONFIG_LWM2M_FIRMWARE_UPDATE_PULL_COAP_PROXY_ADDR="coap://192.168.0.118:5682"' >> $APP/boards/frdm_k64f-local.conf
fi
run west build -s $APP -d build-$APP -b $PLATFORM
run west sign -t imgtool -d build-$APP -- --key mcuboot/root-rsa-2048.pem

if [ -d "$archive" ] ; then
	dst=$archive/$(basename $APP)
	cp zephyr.signed.bin $dst.signed.bin
	cp zephyr.signed.hex $dst.signed.hex
	cp build-mcuboot/zephyr/zephyr.bin $dst-mcuboot.bin
	tar -czf $dst-build-artifacts.tgz build-*
fi
