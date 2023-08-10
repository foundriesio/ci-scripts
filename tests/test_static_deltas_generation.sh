# example: ./tests/test_static_deltas_generation.sh $FACTORY $USER_TOKEN $USER_ID $SECRETS_DIR $BUILD_NUMB $WORK_DIR
# Input params
FACTORY=$1
OSF_TOKEN=$2
# USER_ID = $(fioctl users -f <factory>)
USER_ID=$3
# must have `deltas` file that contains `to` and `froms` dicts, e.g.
#[
# {
#		"to": [
#			"8746add97a01d76cec838f29ab9782fd5ba2a85099eb4569d5ae5b52275f4985",
#			"https://api.foundries.io/projects/msul-dev01/lmp/builds/2071/runs/intel-corei7-64/other/intel-corei7-64-ostree_repo.tar.bz2"
#			],
#		"froms": [
#			[
#				"bc0d3ff32fe90e03f1d572900f6c5d9f40d3173c00910f09c899b4a284e09322",
#				"https://api.foundries.io/projects/msul-dev01/lmp/builds/2070/runs/intel-corei7-64/other/intel-corei7-64-ostree_repo.tar.bz2"
#			],
#		]
#  }
#]
SECRETS_DIR=$4
H_BUILD=$5

WORK_DIR=${6-"$(mktemp -d -t generate-static-deltas-XXXXXXXXXX)"}
echo ">> Work dir: ${WORK_DIR}"
ARCHIVE="${WORK_DIR}/archive"
mkdir -p "${ARCHIVE}"

echo -n "${OSF_TOKEN}" > "${SECRETS_DIR}/osftok"
echo -n "${USER_ID}" > "${SECRETS_DIR}/triggered-by"

CMD=./lmp/generate-static-deltas
H_RUN_URL="https://api.foundries.io/projects/{FACTORY}/lmp/builds/${H_BUILD}/runs/generate/"

docker run -v -it --rm \
  -e FACTORY=$FACTORY \
  -e PYTHONPATH=./ \
  -e H_PROJECT="${FACTORY}/lmp" \
  -e H_RUN_URL="${H_RUN_URL}" \
  -e H_BUILD="${H_BUILD}" \
  -v $PWD:/ci-scripts \
  -v $SECRETS_DIR:/secrets \
  -v $ARCHIVE:/archive \
  -w /ci-scripts \
  foundries/lmp-image-tools "${CMD}"
