#!/bin/sh -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh

LATEST=${LATEST:-latest}

status Launching dockerd
unset DOCKER_HOST
/usr/local/bin/dockerd-entrypoint.sh --experimental --raw-logs >/archive/dockerd.log 2>&1 &
for i in `seq 12 -1 0` ; do
	sleep 1
	docker info >/dev/null 2>&1 && break
	if [ $i = 0 ] ; then
		status Timed out trying to connect to internal docker host
		exit 1
	fi
done

container="hub.foundries.io/lmp-sdk"
# override tag if passed as argument
tags="${LATEST}"
if [ "${tags}" == "latest" ]; then
	# add latest tag
	tags="$(git log -1 --format=%h) ${tags}"
fi

docker_login
for t in ${tags}; do
	run docker build -t ${container}:${t} .
	run docker push ${container}:${t}
done
