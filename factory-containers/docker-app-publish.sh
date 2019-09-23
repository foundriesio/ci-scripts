#!/bin/sh -e
# Copyright (c) 2019 Foundries.io, SPDX-License-Identifier: Apache-2.0
set -o pipefail

HERE=$(dirname $(readlink -f $0))
. $HERE/../helpers.sh

require_params FACTORY

apps=$(ls *.dockerapp 2>/dev/null) || exit 0

run apk --no-cache add git jq

CREDENTIALS=/var/cache/bitbake/credentials.zip
TAG=$(git log -1 --format=%h)

tufrepo=$(mktemp -u -d)

run garage-sign init --repo ${tufrepo} --credentials ${CREDENTIALS}
run garage-sign targets pull --repo ${tufrepo}

cp ${tufrepo}/roles/unsigned/targets.json /archive/targets-before.json

for app in $apps ; do
	sed -i ${app} -e "s/image: hub.foundries.io\/${FACTORY}\/\(.*\):latest/image: hub.foundries.io\/${FACTORY}\/\1:$TAG/g"
	run ${HERE}/ota-dockerapp.py publish ${app} ${CREDENTIALS} ${H_BUILD} ${tufrepo}/roles/unsigned/targets.json
done

run ${HERE}/ota-dockerapp.py add-build ${CREDENTIALS} ${H_BUILD} ${tufrepo}/roles/unsigned/targets.json `ls *.dockerapp`

cp ${tufrepo}/roles/unsigned/targets.json /archive/targets-after.json

echo "Signing local TUF targets"
run garage-sign targets sign --repo ${tufrepo} --key-name targets

echo "Publishing local TUF targets to the remote TUF repository"
run garage-sign targets push --repo ${tufrepo}
