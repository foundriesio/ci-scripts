# Common helper functions for all scripts

set -o pipefail

function indent { sed 's/^/|  /'; echo "|--" ;}
function status { echo == $(date "+%F %T") $* ; }

function run { set -o pipefail; status "Running: $*"; $* 2>&1 | indent ; }

dns_base=$(echo $H_RUN_URL | cut -d/ -f3 | sed -e 's/api.//')
hub_fio="hub.${dns_base}"

function docker_login {
	status "hub url is: $hub_fio"
	status "Doing docker-login to ${hub_fio} with secret"
	docker login ${hub_fio} --username=doesntmatter --password=$(cat /secrets/osftok) | indent

	if [ -f /secrets/container-registries ] ; then
		PYTHONPATH=$HERE/.. $HERE/login_registries /secrets/container-registries
	fi
}

function require_params {
	for x in $* ; do
		eval val='$'$x
		if [ -z $val ] ; then
			echo Missing required parameter: \$$x
			exit 1
		fi
	done
}

function load_extra_certs {
	if [ -d /usr/local/share/ca-certificates ] ; then
		status "Loading extra ca certificates"
		update-ca-certificates
	fi
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
	for i in $(seq 4); do
		run repo init --repo-rev=v2.29.4 --no-clone-bundle -u $* ${REPO_INIT_OVERRIDES} && break
		status "repo init failed with error $?"
		[ $i -eq 4 ] && exit 1
		status "sleeping and trying again"
		sleep $(($i*2))
	done
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
	# 1: Work on a copy
	WORKCOPY="$PWD/.repo/manifests.git.tmp"
	cp -R .repo/manifests.git $WORKCOPY
	pushd $WORKCOPY >/dev/null

	# 2: Replace all tags
	git tag --delete $(git tag) >/dev/null
	git remote set-url origin https://github.com/foundriesio/lmp-manifest
	git fetch origin --tags --quiet

	# 3: Find our base LMP version based on the HEAD
	export LMP_VERSION=$(git describe --tags --abbrev=0 HEAD)
	export LMP_VERSION_CACHE="$LMP_VERSION"
	if [[ "${H_PROJECT}" == "lmp" ]] || [ -v LMP_VERSION_CACHE_DEV ] ; then
		# Public LmP build - we are building for the *next* release
		LMP_VERSION_CACHE=$(( $LMP_VERSION_CACHE + 1 ))
	fi
	status "Base LmP cache version detected as: $LMP_VERSION_CACHE"

	# 4: cleanup
	popd >/dev/null
	rm -rf $WORKCOPY
}
