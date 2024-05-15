#!/bin/sh -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh

TAG=$(git log -1 --format=%h)

status Launching dockerd
unset DOCKER_HOST
/usr/local/bin/dockerd-entrypoint.sh --experimental --raw-logs >/archive/dockerd.log 2>&1 &
for i in `seq 12` ; do
	sleep 1
	docker info >/dev/null 2>&1 && break
	if [ $i = 12 ] ; then
		status Timed out trying to connect to internal docker host
		exit 1
	fi
done

container="hub.foundries.io/lmp-sdk"
tagged="${container}:${TAG}"
latest="${container}:latest"

docker_login

run docker build -t ${tagged} -t ${latest} .
run docker push ${tagged}
run docker push ${latest}
