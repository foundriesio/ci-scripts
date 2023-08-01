# example: ./tests/test_static_deltas_generation.sh $FACTORY $USER_TOKEN $USER_ID ./secrets $BUILD_NUMB $PWD/work-dir
# Input params
FACTORY=$1
OSF_TOKEN=$2
# FIO_USER_ID = $(fioctl users -f <factory>)
USER_ID=$3
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
