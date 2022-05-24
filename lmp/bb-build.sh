#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params IMAGE

start_ssh_agent

source setup-environment build

if [ "${APP_PRELOAD_WITHIN_OE_BUILD}" = "1" ]; then
	PYTHONPATH=$HERE/.. $HERE/../apps/login_registries /secrets/container-registries
	docker login hub.foundries.io --username=doesntmatter --password=$(cat "${APP_PRELOAD_TOKEN_FILE}")
fi

# Parsing first, to stop in case of parsing issues
bitbake -p

# Global and image specific envs
bitbake -e > ${archive}/bitbake_global_env.txt
bitbake -e ${IMAGE} > ${archive}/bitbake_image_env.txt

# Setscene (cache), failures not critical
bitbake --setscene-only ${IMAGE} || true

bitbake -D ${IMAGE}
