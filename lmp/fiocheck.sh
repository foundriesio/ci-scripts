#!/bin/bash

HERE=$(dirname $(readlink -f $0))
CHECK_BIN="${FIO_CHECK_BIN-/usr/bin/fiocheck}"

"${HERE}/run-with-retry.sh" "${CHECK_BIN}" $@

