#!/bin/sh -e
# Copyright (c) 2019 Foundries.io, SPDX-License-Identifier: Apache-2.0
#
# This script will handle the follow scenarios for building containers
#   * If NOCACHE flag is set, it will rebuild all container images without cache.
#   * If NOCACHE flag is _NOT_ set, it will only rebuild containers in which
#     files have changed. This is the default behavior.
#   * If the image cache cannot be pulled, a fresh rebuild will be forced.
#   * If the image cache _CAN_ be pulled, this cached image is tagged with
#     the current SHA. This allows the subsequent docker-app publish to provide
#     an update which has a valid container image in the registry.
set -o pipefail

HERE=$(dirname $(readlink -f $0))
. $HERE/../helpers.sh

require_params FACTORY

run apk --no-cache add file git

ARCH=amd64
file /bin/busybox | grep -q aarch64 && ARCH=arm64 || true
file /bin/busybox | grep -q armhf && ARCH=arm || true

manifest_arch=$ARCH
[ $manifest_arch = "arm" ] && manifest_arch=armv6
status Grabbing manifest-tool for $manifest_arch
wget -O /bin/manifest-tool https://github.com/estesp/manifest-tool/releases/download/v0.8.0/manifest-tool-linux-$manifest_arch
chmod +x /bin/manifest-tool

if [ -z "$IMAGES" ] ; then
	IMAGES=$(find * -prune -type d)
fi

status Launching dockerd
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

TAG=$(git log -1 --format=%h)
LATEST=${OTA_LITE_TAG-"latest"}

if [ -f /secrets/osftok ] ; then
	mkdir -p $HOME/.docker
fi

# TODO -- pull submodules here?! 
# or add to build configuration?
# git submodule update --init --recursive
echo '<testsuite name="unit-tests">' > /archive/junit.xml
trap 'echo "</testsuite>" >> /archive/junit.xml' TERM INT EXIT

for x in $IMAGES ; do
	# Skip building things that end with .disabled
	echo $x | grep -q -E \\.disabled$ && continue
	unset CHANGED SKIP_ARCHS MANIFEST_PLATFORMS EXTRA_TAGS_$ARCH TEST_CMD

	# If NOCACHE is not set, only build images that have changed.
	if [ -z "$NOCACHE" ] ; then
		no_op_tag=0
		CHANGED=$(git diff --name-only $GIT_OLD_SHA..$GIT_SHA $x/)
		if [[ ! -z "$CHANGED" ]]; then
			status "Detected changes to $x"
		else
			status "No changes to $x, tagging only"
			no_op_tag=1
		fi
	fi

	conf=$x/docker-build.conf
	if [ -f $conf ] ; then
		echo "Sourcing docker-build.conf for build rules in $x"
		. $conf
	fi

	# check to see if we should skip building this image`
	found=0
	for a in $SKIP_ARCHS ; do
		if [ "$a" = "$ARCH" ] ; then
			status "Skipping build of $x on $ARCH"
			found=1
			break
		fi
	done
	[ $found -eq 1 ] && continue

	# allow the docker-build.conf to override our manifest platforms
	MANIFEST_PLATFORMS="${MANIFEST_PLATFORMS-linux/amd64,linux/arm,linux/arm64}"

	ct_base="hub.foundries.io/${FACTORY}/$x"

	auth=0
	if [ -f /secrets/osftok ] ; then
		status "Doing docker-login to hub.foundries.io with secret"
		docker login hub.foundries.io --username=doesntmatter --password=$(cat /secrets/osftok) | indent
		# sanity check and pull in a cached image if it exists. if it can't be pulled set no_op_tag to 0.
		run docker pull ${ct_base}:latest || no_op_tag=0
		if [ $no_op_tag -eq 0 ] && [ -z "$CHANGED" ]; then
			echo "WARNING - no cached image found, forcing a rebuild"
		fi
		auth=1
	fi

  # ..more robust logic here...?
  if [ -z "$DOCKERFILE" ] ; then
    echo 'NOT using custom context.'
    DOCKERFILE="Dockerfile"
    BUILD_CONTEXT="."
	  cd $x
  else
    echo "Using custom build context $BUILD_CONTEXT with dockerfile $DOCKERFILE"
  fi
  
	if [ $no_op_tag -eq 1 ] ; then
		status Tagging docker image $x for $ARCH
		run docker tag ${ct_base}:latest ${ct_base}:$TAG-$ARCH
	else
		if [ -z "$NOCACHE" ] ; then
			status Building docker image $x for $ARCH with cache
			run docker build --label "jobserv_build=$H_BUILD" --cache-from ${ct_base}:latest -f $DOCKERFILE -t ${ct_base}:$TAG-$ARCH --force-rm $BUILD_CONTEXT
		else
			status Building docker image $x for $ARCH with no cache
			run docker build --label "jobserv_build=$H_BUILD" --no-cache -f $DOCKERFILE -t ${ct_base}:$TAG-$ARCH --force-rm $BUILD_CONTEXT
		fi
	fi

	if [ $auth -eq 1 ] ; then
		run docker push ${ct_base}:$TAG-$ARCH

		var="EXTRA_TAGS_$ARCH"
		for t in $(eval echo "\$$var") ; do
			status "Tagging and pushing extra tag defined in docker-build.conf: $t"
			run docker tag ${ct_base}:$TAG-$ARCH ${ct_base}:$TAG-$t
			run docker push ${ct_base}:$TAG-$t
		done

		run manifest-tool push from-args \
			--platforms $MANIFEST_PLATFORMS \
			--template ${ct_base}:$TAG-ARCH \
			--target ${ct_base}:$TAG || true
		run manifest-tool push from-args \
			--platforms $MANIFEST_PLATFORMS \
			--template ${ct_base}:$TAG-ARCH \
			--target ${ct_base}:$LATEST || true
	else
		echo "osftoken not provided, skipping publishing step"
	fi

	if [ -n "$TEST_CMD" ] ; then
		status Running test command inside container: $TEST_CMD
		echo "<testcase name=\"test-$x\">" >> /archive/junit.xml
		echo "   docker run --rm --entrypoint=\"\" ${ct_base}:$TAG-$ARCH $TEST_CMD"
		if ! docker run --rm --entrypoint="" ${ct_base}:$TAG-$ARCH $TEST_CMD > /archive/$x-test.log 2>&1 ; then
			status "Testing for $x failed"
			echo "<failure>" >> /archive/junit.xml
			cat /archive/$x-test.log | sed -e 's/</\&lt;/g' -e 's/>/\&gt;/g' >> /archive/junit.xml
			echo "</failure>" >> /archive/junit.xml
		fi
		echo "</testcase>" >> /archive/junit.xml
	fi
	cd ..
done
