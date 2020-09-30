#!/bin/sh -e

PYTHONPATH=./:factory-containers/ python -m unittest discover -s tests
