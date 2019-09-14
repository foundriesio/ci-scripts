#!/bin/sh -e

## This script is run when the container-manifest project changes. It
## tags all the images declared by the default.xml SHA. Its sort of
## a way to mark a set of containers as an RC build.

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh

require_params PRODUCT

run apk --no-cache add file git perl-xml-xpath

DOCKER_TLS_CERTDIR= /usr/local/bin/dockerd-entrypoint.sh --raw-logs >/archive/dockerd.log 2>&1 &
unset DOCKER_HOST
for i in `seq 10` ; do
	sleep 1
	docker info >/dev/null 2>&1 && break
	if [ $i = 10 ] ; then
		echo 'Timed out trying to connect to internal docker host.' >&2
		exit 1
	fi
done

ARCH_LIST="amd64 arm64 arm"
NAME=$PRODUCT-containers

git fetch origin refs/notes/*:refs/notes/*
git notes --ref $NAME show > /archive/junit.xml || echo "Unable to find test results from git-notes"
cp default.xml /archive/manifest.pinned.xml

# Determine the container's tag:
GIT_SHA=$(xpath -e "string(/manifest/project[@name=\"${PRODUCT}-containers\"]/@revision)" default.xml 2>/dev/null)
TAG=$(echo ${GIT_SHA} | cut -c 1-6)
status "GIT_SHA(${GIT_SHA}) DOCKER TAG(${TAG})"

run git clone https://github.com/foundriesio/$NAME.git
cd $NAME
run git checkout $GIT_SHA

IMAGES=$(find * -prune -type d)

if [ -f /secrets/osftok ] ; then
	docker login hub.foundries.io --username=gavin --password=$(cat /secrets/osftok)
else
	if [ -z $DRYRUN ] ; then
		echo "ERROR: Missing required secret: osftok"
		exit 1
	fi
fi

REGISTRY=hub.foundries.io
RC_TAG="rcbuild_${H_BUILD}"

WORK=$(($(echo $IMAGES | wc -w) * $(echo $ARCH_LIST | wc -w)))
COUNTER=0
for x in $IMAGES ; do
	for a in $ARCH_LIST; do
		run docker pull $REGISTRY/$x:$TAG-$a
		rctag="${REGISTRY}/${x}:${RC_TAG}-$a"
		run docker tag $REGISTRY/$x:$TAG-$a $rctag
		[ -z $DRYRUN ] || echo DRYRUN: docker push $rctag
		[ -z $DRYRUN ] && run docker push $rctag

		let COUNTER=COUNTER+1
		status "Published $COUNTER / $WORK items"
	done
done
