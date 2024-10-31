#!/bin/bash

HERE=$(dirname $(readlink -f $0))
PUSH_BIN="${FIO_PUSH_BIN-/usr/bin/fiopush}"

"${HERE}/run-with-retry.sh" "${PUSH_BIN}" $@
