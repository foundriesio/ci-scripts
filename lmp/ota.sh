#!/bin/sh -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh

host_tests="/secrets/download_hosts_tests"
if [ -f $host_tests ] ; then
	echo "Overriding hosts_test.py with script from secrets"
	chmod +x $host_tests
	$host_tests > HERE/host_tests.py
fi

PYTHONUNBUFFERED=1 PYTHONPATH=$HERE:$HERE/../ python3 $HERE/ota_test.py
