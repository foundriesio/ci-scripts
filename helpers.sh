# Common helper functions for all scripts

set -o pipefail

function indent { sed 's/^/|  /'; echo "|--" ;}
function status { echo == $(date "+%F %T") $* ; }

function run { status "Running: $*"; $* 2>&1 | indent ; }

function require_params {
	for x in $* ; do
		eval val='$'$x
		if [ -z $val ] ; then
			echo Missing required parameter: \$$x
		fi
	done
}
