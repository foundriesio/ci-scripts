#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params PLATFORM PYOCD_BOARD_NAME H_TRIGGER_URL GIT_URL GIT_SHA

if [ -z $SUDO_USER ] && [ $(id -u) -ne 0 ] ; then
	status "Running script with: sudo $0 $*"
	exec sudo -E $0 $*
fi

if [ ! -d /repo ] ; then
	status "Checking out zephyr source"
	run git_config
	run git clone $GIT_URL /repo
	cd repo
	run git branch jobserv-run $GIT_SHA
	run git checkout jobserv-run
else
	cd /repo
fi


status "Applying board-id patch"
git_config
run git fetch https://github.com/zephyrproject-rtos/zephyr.git pull/11851/head:board-id
run git cherry-pick f4920ec0c869c4292502acb80cfc799a4c52bdc9
run git cherry-pick 9d8490620ef3b956584b9ef87e084bfba29deee0

status "Getting test list"
run wget -O /tmp/test-list ${H_TRIGGER_URL}test-list
run wget -O /tmp/outdir.tgz --progress=dot -e dotbytes=1M ${H_TRIGGER_URL}outdir.tgz
tar -C /tmp -xzf /tmp/outdir.tgz

status "Installing dependencies"
python3 -c "import pyudev" || run pip3 install pyudev==0.21.0
run pip3 install -U west

status "Probing for a board named: $PYOCD_BOARD_NAME"
board=$(sudo $(dirname $(readlink -f $0))/pyocd-probe-for $PYOCD_BOARD_NAME)
board_tty=$(echo $board | cut -d\| -f1)
board_uid=$(echo $board | cut -d\| -f2)

status "Probed board tty($board_tty) id($board_uid)"

. zephyr-env.sh
cd ..
run west init -l $ZEPHYR_BASE
run west update
cd $ZEPHYR_BASE

status "Running tests"
set -x
sanitycheck  \
	--platform $PLATFORM \
	--inline-logs \
	--outdir /tmp/outdir \
	--enable-slow \
	--verbose \
	--ninja \
	--no-clean \
	--load-tests /tmp/test-list \
	--test-only \
	--device-testing \
	--device-serial $board_tty \
	--west-flash-option=--board-id=$board_uid \
	-e kernel \
|| true

cp ./scripts/sanity_chk/last_sanity.xml /archive/junit.xml
