#!/bin/bash -e

source setup-environment build

cat << EOFEOF >> conf/auto.conf

# Disable non compatible classes for oe-selftest
INHERIT:remove = "buildhistory"
INHERIT:remove = "rm_work"
INHERIT:remove = "create-spdx"
INHERIT:remove = "archiver"
EOFEOF

# Save the reproducible test results
export OEQA_DEBUGGING_SAVED_OUTPUT="${archive}/selftest"

oe-selftest $OS_SELFTEST --newbuilddir $PWD
