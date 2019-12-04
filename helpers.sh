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
}

function repo_sync {
	status "Repo syncing sources..."

	git_config
	if [ -f /secrets/git.http.extraheader ] ; then
		domain=$(echo $GIT_URL | cut -d/  -f3)
		status "Adding git config extraheader for $domain"
		git config --global http.https://${domain}.extraheader "$(cat /secrets/git.http.extraheader)"
	fi
	run repo init --no-clone-bundle -u $* ${REPO_INIT_OVERRIDES}
	run repo sync
	if [ -d "$archive" ] ; then
		status "Generating pinned manifest"
		repo manifest -r -o $archive/manifest.pinned.xml
		cp .repo/manifest.xml $archive/manifest.xml
	fi
}
