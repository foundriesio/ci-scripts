# Common helper functions for all scripts

set -o pipefail

function indent { sed 's/^/|  /'; echo "|--" ;}
function status { echo == $(date "+%F %T") $* ; }

function run { set -o pipefail; status "Running: $*"; $* 2>&1 | indent ; }

function require_params {
	for x in $* ; do
		eval val='$'$x
		if [ -z $val ] ; then
			echo Missing required parameter: \$$x
			exit 1
		fi
	done
}

function git_config {
	git config user.email 2>/dev/null || git config --global user.email "gavin@foundries.io"
	git config user.name 2>/dev/null || git config --global user.name "cibot"
	# https://github.blog/2022-04-12-git-security-vulnerability-announced/
	git config --system --add safe.directory /srv/oe/layers/meta-subscriber-overrides
	git config --system --add safe.directory /srv/oe/.repo/manifests
	git config --system --add safe.directory /repo
}

function start_ssh_agent {
	keys=$(ls /secrets/ssh-*.key 2>/dev/null || true)
	if [ -n "$keys" ] ; then
		status Found ssh keys, starting an ssh-agent
		mkdir -p $HOME/.ssh
		eval `ssh-agent`
		for x in $keys ; do
			echo " Adding $x"
			key=$HOME/.ssh/$(basename $x)
			cp $x $key
			chmod 700 $key
			ssh-add $key
		done
		if [ -f /secrets/ssh-known_hosts ] ; then
			status " Adding known hosts file"
			ln -s /secrets/ssh-known_hosts $HOME/.ssh/known_hosts
		fi
	fi
}

function repo_sync {
	status "Repo syncing sources..."

	if [ -f /secrets/git.http.extraheader ] ; then
		domain=$(echo $GIT_URL | cut -d/  -f3)
		status "Adding git config extraheader for $domain"
		git config --global http.https://${domain}.extraheader "$(cat /secrets/git.http.extraheader)"
	fi
	run repo init --repo-rev=v2.29.4 --no-clone-bundle -u $* ${REPO_INIT_OVERRIDES}
	for i in $(seq 4); do
		run timeout 4m repo sync && break
		if [ $? -eq 124 ] ; then
			msg="Command timed out"
			if [ $i -ne 4 ] ; then
				msg="${msg}, trying again"
			fi
			status ${msg}
		else
			exit $?
		fi
	done
	if [ -d "$archive" ] ; then
		status "Generating pinned manifest"
		repo manifest -r -o $archive/manifest.pinned.xml
		cp .repo/manifest.xml $archive/manifest.xml
	fi
}

function set_base_lmp_version {
	# Detect the base LmP version we are building on
	# A user may have place arbitrary tags into their lmp-manifest and we
	# don't want to accidentally pick one of them up. Git doesn't really
	# distinguish where tags come from, so:

	# 1: Delete all tags
	git --git-dir .repo/manifests.git tag | xargs git --git-dir .repo/manifests.git tag -d > /dev/null

	# 2: Get the LMP tags
	run git --git-dir .repo/manifests.git remote add upstream https://github.com/foundriesio/lmp-manifest
	run git --git-dir .repo/manifests.git fetch --tags upstream

	# 3: Find our base LMP version based on the HEAD
	export LMP_VER=$(git --git-dir .repo/manifests.git describe HEAD --tags --abbrev=0)
	if [[ "${H_PROJECT}" == "lmp" ]] ; then
		# Public LmP build - we are building for the *next* release
		LMP_VER=$(( $LMP_VER + 1 ))
	fi

	# 4: Delete all tags again
	git --git-dir .repo/manifests.git tag | xargs git --git-dir .repo/manifests.git tag -d > /dev/null

	# 5: Restore orginal tags - the build may need them
	run git --git-dir .repo/manifests.git fetch --tags
	status "Base LmP version detected as: $LMP_VER"
}
