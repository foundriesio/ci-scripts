#!/bin/sh -e
# Copyright (c) 2019 Foundries.io, SPDX-License-Identifier: Apache-2.0
#
# This script will handle the follow scenarios for building containers
#   * If NOCACHE flag is set, it will rebuild all container images without cache.
#   * If NOCACHE flag is _NOT_ set, it will only rebuild containers in which
#     files have changed. This is the default behavior.
#   * If the image cache cannot be pulled, a fresh rebuild will be forced.
#   * If the image cache _CAN_ be pulled, this cached image is tagged with
#     the current SHA. This allows the subsequent app publishing functionality to provide
#     an update which has a valid container image in the registry.
set -o pipefail

HERE=$(dirname $(readlink -f $0))
. $HERE/../helpers.sh

require_params FACTORY

export DOCKER_BUILDKIT=1
BUILDKIT_VERSION="${BUILDKIT_VERSION-v0.10.3}"

MANIFEST_PLATFORMS_DEFAULT="${MANIFEST_PLATFORMS_DEFAULT-linux/amd64,linux/arm,linux/arm64}"
status Default container platforms will be: $MANIFEST_PLATFORMS_DEFAULT

if [ -f /secrets/docker_host_config.json ] ; then
	mkdir -p $HOME/.docker
	cp /secrets/docker_host_config.json $HOME/.docker/config.json
fi

ARCH=amd64
file /bin/busybox | grep -q aarch64 && ARCH=arm64 || true
file /bin/busybox | grep -q armhf && ARCH=arm || true

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

DOCKER_BUILDX="1"
docker_build="docker buildx build"

TAG=$(git log -1 --format=%h)
LATEST=${OTA_LITE_TAG-"latest"}
LATEST=$(echo $LATEST | cut -d: -f1 | cut -d, -f1)  # Take into account advanced tagging

pbc=pre-build.conf
if [ -f $pbc ] ; then
  echo "Sourcing pre-build.conf."
  . $pbc
fi

if [ -f /secrets/container-registries ] ; then
	PYTHONPATH=$HERE/.. $HERE/login_registries /secrets/container-registries
fi

if [ -z "$IMAGES" ] ; then
	# Look through the first level of subdirectories for Dockerfile
	IMAGES=$(find ./ -mindepth 2 -maxdepth 2 -name Dockerfile | cut -d / -f2)
fi


if [ -f /secrets/osftok ] ; then
	mkdir -p $HOME/.docker
fi

echo '<testsuite name="unit-tests">' > /archive/junit.xml
trap 'echo "</testsuite>" >> /archive/junit.xml' TERM INT EXIT

total=$(echo $IMAGES | wc -w)
total=$((total*3)) # 3 steps per container: build, push, test*manifest
completed=-3  # we increment on the first step of the first loop.

REPO_ROOT=$(pwd)
for x in $IMAGES ; do
	completed=$((completed+3))
	# Skip building things that end with .disabled
	echo $x | grep -q -E \\.disabled$ && continue
	unset CHANGED SKIP_ARCHS MANIFEST_PLATFORMS EXTRA_TAGS_$ARCH TEST_CMD BUILD_CONTEXT DOCKERFILE

	conf=$x/docker-build.conf
	if [ -f $conf ] ; then
		echo "Sourcing docker-build.conf for build rules in $x"
		. $conf
	fi

	# If NOCACHE is not set, only build images that have changed.
	if [ -z "$NOCACHE" ] ; then
		no_op_tag=0
		# If we are using buildx, don't try to guess what has changed
		if [ -z "$DOCKER_BUILDX" ] ; then
			# If we cannot obtain the diff, force the build
			CHANGED=$(git diff --name-only $GIT_OLD_SHA..$GIT_SHA $x/${BUILD_CONTEXT} || echo FORCE_BUILD)
			if [[ ! -z "$CHANGED" ]]; then
				status "Detected changes to $x"
			else
				status "No changes to $x, tagging only"
				no_op_tag=1
			fi
		fi
	fi

	# check to see if we should skip building this image`
	found=0
	for a in $SKIP_ARCHS ; do
		if [ "$a" = "$ARCH" ] ; then
			status "Skipping build of $x on $ARCH"
			found=1
			echo "Build step $((completed+3)) of $total is complete"
			break
		fi
	done
	[ $found -eq 1 ] && continue

	# We need a new context for each container we build
	run docker buildx create --driver-opt image=moby/buildkit:${BUILDKIT_VERSION} --use

	# allow the docker-build.conf to override our manifest platforms
	MANIFEST_PLATFORMS="${MANIFEST_PLATFORMS-${MANIFEST_PLATFORMS_DEFAULT}}"

	ct_base="hub.foundries.io/${FACTORY}/$x"

	auth=0
	if [ -f /secrets/osftok ] ; then
		status "Doing docker-login to hub.foundries.io with secret"
		docker login hub.foundries.io --username=doesntmatter --password=$(cat /secrets/osftok) | indent
		auth=1
	fi

	if [ $no_op_tag -eq 1 ] ; then
		status Tagging docker image $x for $ARCH
		run docker tag ${ct_base}:${LATEST} ${ct_base}:$TAG-$ARCH
	else
		docker_cmd="$docker_build -t ${ct_base}:$TAG-$ARCH -t ${ct_base}:$LATEST-$ARCH --force-rm"
		if [ -z "$NOCACHE" ] ; then
			status Building docker image $x for $ARCH with cache
			docker_cmd="$docker_cmd  --cache-from ${ct_base}:${LATEST}"
			docker_cmd="${docker_cmd}-${ARCH}_cache"
		else
			status Building docker image $x for $ARCH with no cache
			docker_cmd="$docker_cmd  --no-cache"
		fi

		docker_cmd="$docker_cmd --push --cache-to type=registry,ref=${ct_base}:${LATEST}-${ARCH}_cache,mode=max"

		if [ -n "$DOCKER_SECRETS" ] ; then
			status "DOCKER_SECRETS defined - building --secrets for $(ls /secrets)"
			for secret in `ls /secrets` ; do
				docker_cmd="$docker_cmd --secret id=${secret},src=/secrets/${secret}"
			done
		fi

		db_args_file="$REPO_ROOT/$x/.docker_build_args"
		if [ -f $db_args_file ] ; then
			status "Adding .docker_build_args"
			docker_cmd="$docker_cmd $(cat $db_args_file | sed '/^[[:space:]]*$/d' | sed '/^#/d' | sed 's/^/--build-arg /' | paste -s -d " ")"
		fi

		DOCKERFILE="$REPO_ROOT/$x/${DOCKERFILE-Dockerfile}"
		if [ -n "$BUILD_CONTEXT" ] ; then
			status "Using custom build context $BUILD_CONTEXT"
			BUILD_CONTEXT="$REPO_ROOT/$x/${BUILD_CONTEXT}"
		else
			BUILD_CONTEXT="$REPO_ROOT/$x/"
		fi
		# we have to use eval because the some parts of docker_cmd are
		# variables quotes with spaces: --build-arg "foo=bar blah"
		run eval "$docker_cmd -f $DOCKERFILE $BUILD_CONTEXT"

	        # Publish a list of md5sum checksums for the source code of each image build
	        find ${BUILD_CONTEXT} -type f -exec md5sum '{}' \; > /archive/${x}-md5sum.txt
	fi
	echo "Build step $((completed+1)) of $total is complete"

	if [ $auth -eq 1 ] ; then
		run docker manifest create ${ct_base}:${H_BUILD}_$TAG ${ct_base}:$TAG-$ARCH
		run docker manifest create ${ct_base}:${LATEST} ${ct_base}:$TAG-$ARCH

		var="EXTRA_TAGS_$ARCH"
		for t in $(eval echo "\$$var") ; do
			status "Handling manifest logic for $var"

			tmp=$HOME/.docker/manifests/hub.foundries.io_${FACTORY}_${x}-${H_BUILD}_${TAG}
			cp ${tmp}/hub.foundries.io_${FACTORY}_${x}-${TAG}-${ARCH} ${tmp}/hub.foundries.io_${FACTORY}_${x}-${TAG}-${t}
			run docker manifest annotate ${ct_base}:${H_BUILD}_${TAG} ${ct_base}:${TAG}-$t --arch $t

			tmp=$HOME/.docker/manifests/hub.foundries.io_${FACTORY}_${x}-${LATEST}
			cp ${tmp}/hub.foundries.io_${FACTORY}_${x}-${TAG}-${ARCH} ${tmp}/hub.foundries.io_${FACTORY}_${x}-${TAG}-${t}
			run docker manifest annotate ${ct_base}:${LATEST} ${ct_base}:${TAG}-$t --arch $t
		done

		echo "Build step $((completed+2)) of $total is complete"

	else
		echo "osftoken not provided, skipping publishing step"
	fi

	status "Doing a syft SBOM scan"
	sbom_dst=/archive/sboms/${ct_base}/${ARCH}.spdx.json
	mkdir -p $(dirname $sbom_dst)
	syft ${ct_base}:$TAG-$ARCH -o spdx-json > $sbom_dst

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
	echo "Build step $((completed+3)) of $total is complete"
done

# Store the manifest so we can use them in the publish run. A brand new
# factory may not have built any containers, so ensure the directory exists
[ -d $HOME/.docker/manifests ] && mv $HOME/.docker/manifests /archive/manifests || echo 'no manifests to archive'

PYTHONPATH=${HERE}/.. python3 ${HERE}/generate_non_factory_sboms.py --arch=$ARCH
