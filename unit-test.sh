#!/bin/sh -e

PYTHONPATH=./:factory-containers/ python3 -m unittest discover -s tests
