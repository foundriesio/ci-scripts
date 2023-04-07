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
PYTHONPATH=./ python3 -m unittest discover -v -s tests
