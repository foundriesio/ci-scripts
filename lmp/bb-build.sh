#!/bin/bash -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh
require_params IMAGE

keys=$(ls /secrets/ssh-*.key 2>/dev/null || true)
if [ -n "$keys" ] ; then
	status Found ssh keys, starting an ssh-agent
	eval `ssh-agent`
	for x in $keys ; do
		echo " Adding $x"
		ssh-add $x
	done
	if [ -f /secrets/ssh-known_hosts ] ; then
		status " Adding known hosts file"
		mkdir -p $HOME/.ssh
		ln -s /secrets/ssh-known_hosts $HOME/.ssh/known_hosts
	fi
fi

source setup-environment build

bitbake -D ${IMAGE}

bitbake -e | grep "^DEPLOY_DIR="| cut -d'=' -f2 | tr -d '"' > deploy_dir
