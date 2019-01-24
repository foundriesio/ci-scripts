#!/bin/sh -e

HERE=$(dirname $(readlink -f $0))
source $HERE/../helpers.sh

 PYTHONUNBUFFERED=1 PYTHONPATH=$HERE:$HERE/../ python3 $HERE/ota_test.py
