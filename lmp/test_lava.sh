#!/bin/bash -eu

HERE=$(dirname $(readlink -f $0))
TMPDIR=${TMPDIR-/tmp}

tmpdir=$(mktemp -p $TMPDIR -d test_build.XXXX)
trap "echo removing tempdir; rm -rf $tmpdir" TERM INT EXIT

cd $tmpdir


parent=$(dirname $HERE)
docker run --rm -it -w $PWD \
	-v $PWD:/archive \
	-v $PWD:$PWD \
	-v $parent:$parent \
	-v /bin/true:/usr/local/bin/generate-public-url \
	-v /bin/true:/usr/local/bin/lava-submit \
	-e MACHINE=beaglebone-yocto \
	hub.foundries.io/lmp-sdk $HERE/lava.sh

cat >validate.py <<EOF
import sys
import yaml

yaml.load(sys.stdin)
EOF
python3 validate.py < lmp-beaglebone-yocto.yml
