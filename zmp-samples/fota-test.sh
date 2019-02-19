#!/bin/sh -ex

if [ "$PLATFORM" = "nrf52_blenano2" ] ; then
	BOARD_NAME="RedBearLab-BLE-Nano2"
fi
if [ "$PLATFORM" = "reel_board" ] ; then
	BOARD_NAME="reel board"
fi

[ -z "$BOARD_NAME" ] && (echo "Invalid PLATFORM=$PLATFORM"; exit 1)

export LOG_DIR=/archive
python3 -m mp_e2e.sanity ZMP_BUILD=$H_BUILD BOARD_NAME="$BOARD_NAME" \
	CI_PROJECT=$H_PROJECT \
	CI_RUN=$(basename $H_TRIGGER_URL)
