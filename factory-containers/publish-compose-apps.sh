#!/bin/sh -e
# Copyright (c) 2019 Foundries.io, SPDX-License-Identifier: Apache-2.0
set -o pipefail

HERE=$(dirname $(readlink -f $0))
. $HERE/../helpers.sh

require_params FACTORY H_BUILD

pbc=pre-build.conf
if [ -f $pbc ] ; then
  echo "Sourcing pre-build.conf."
  . $pbc
fi

status "Launching dockerd"
unset DOCKER_HOST
DOCKER_TLS_CERTDIR= /usr/local/bin/dockerd-entrypoint.sh --raw-logs >/archive/dockerd.log 2>&1 &
for i in `seq 12` ; do
  sleep 1
  docker info >/dev/null 2>&1 && break
  if [ $i = 12 ] ; then
    status Timed out trying to connect to internal docker host
    exit 1
  fi
done

status Doing docker-login to hub.foundries.io with secret
docker login hub.foundries.io --username=doesntmatter --password=$(cat /secrets/osftok) | indent

export PYTHONPATH=${HERE}/../

status Dowloading "compose-ref" for publishing apps
run wget -O /usr/local/bin/compose-publish https://storage.googleapis.com/subscriber_registry/compose-publish
chmod +x /usr/local/bin/compose-publish


CREDENTIALS=$(mktemp)
$HERE/../create-creds /var/cache/bitbake/credentials.zip $CREDENTIALS
export TAG=$(git log -1 --format=%h)

tufrepo=$(mktemp -u -d)

run garage-sign init --repo ${tufrepo} --credentials ${CREDENTIALS}
run garage-sign targets pull --repo ${tufrepo}

cp ${tufrepo}/roles/unsigned/targets.json /archive/targets-before.json

run ${HERE}/publish-compose-apps.py --targets ${tufrepo}/roles/unsigned/targets.json

cp ${tufrepo}/roles/unsigned/targets.json /archive/targets-after.json

echo "Signing local TUF targets"
run garage-sign targets sign --repo ${tufrepo} --key-name targets

echo "Publishing local TUF targets to the remote TUF repository"
run garage-sign targets push --repo ${tufrepo}
