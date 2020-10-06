#!/bin/sh -e

PYTHONPATH=./ python3 -m unittest discover -v -s tests
