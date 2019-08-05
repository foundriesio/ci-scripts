#!/bin/sh -e
# Copyright (c) 2019 Foundries.io, SPDX-License-Identifier: Apache-2.0
set -o pipefail

HERE=$(dirname $(readlink -f $0))
. $HERE/../helpers.sh

require_params FACTORY

run apk --no-cache add git jq

CREDENTIALS=/var/cache/bitbake/credentials.zip
TAG=$(git log -1 --format=%h)

tufrepo=$(mktemp -u -d)

run garage-sign init --repo ${tufrepo} --credentials ${CREDENTIALS}
run garage-sign targets pull --repo ${tufrepo}

cp ${tufrepo}/roles/unsigned/targets.json /archive/targets-before.json

apps=$(ls *.dockerapp)
for app in $apps ; do
	sed -i ${app} -e "s/image: hub.foundries.io\/${FACTORY}\/\(.*\):latest/image: hub.foundries.io\/${FACTORY}\/\1:$TAG/g"
	run ${HERE}/ota-dockerapp.py publish ${app} ${CREDENTIALS} ${H_BUILD} ${tufrepo}/roles/unsigned/targets.json
done

	# there are two outcomes when pushing apps:
	# 1) the repo has online keys and the targets.json on the server was
	#    updated
	# 2) we have offline keys, and the script updated the local copy
	#    of targets.json
	# we can't really distinguish which case we are in. Pulling isn't too
	# terrible to make things work for now. However:
	# TODO once everyone has offline keys, we can remove this junk:
	echo "Pulling updated TUF targets from the remote TUF repository"
	cp ${tufrepo}/roles/unsigned/targets.json /tmp/targets.json
	run garage-sign targets pull --repo ${tufrepo}
	targets_version=$(jq .version ${tufrepo}/roles/unsigned/targets.json)
	mv /tmp/targets.json ${tufrepo}/roles/unsigned/targets.json

run ${HERE}/ota-dockerapp.py add-build ${CREDENTIALS} ${H_BUILD} ${tufrepo}/roles/unsigned/targets.json ${targets_version} `ls *.dockerapp`

cp ${tufrepo}/roles/unsigned/targets.json /archive/targets-after.json

echo "Signing local TUF targets"
run garage-sign targets sign --repo ${tufrepo} --key-name targets

echo "Publishing local TUF targets to the remote TUF repository"
run garage-sign targets push --repo ${tufrepo}
