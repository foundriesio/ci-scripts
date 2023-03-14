#!/bin/bash -e

source setup-environment build

# The oe-selftest reproducible is build in two step (A and B) and sharing
# the same deploy dir will cause some colisions when creating the packages
# so use the default bitbake settings that is inside the TMP dir
sed -i -e 's/^DEPLOY_DIR/#&/' conf/site.conf

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
