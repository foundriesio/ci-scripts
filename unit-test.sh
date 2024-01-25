#!/bin/sh -e

VENV_DIR=$(mktemp -d -p $PWD)
python3 -m venv "${VENV_DIR}"
source "${VENV_DIR}/bin/activate"
pip install -r requirements-dev.txt

function cleanup {
  rm -rf "${VENV_DIR}"
  echo "Deleted virtual env directory ${VENV_DIR}"
}

trap cleanup EXIT

# run tests
H_RUN_URL="https://api.foundries.io/projects/factory/lmp/builds/1/runs/some-run" PYTHONPATH=./ python3 -m unittest discover -v -s tests
