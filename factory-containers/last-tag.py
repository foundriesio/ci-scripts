#!/usr/bin/python3
import os
import subprocess
import time
import logging
import sys

import requests

from helpers import secret

URL = os.environ.get('HUB_URL', 'https://hub.foundries.io')

logging.basicConfig(
    level='INFO', format='%(asctime)s %(levelname)s: %(message)s')
log = logging.getLogger('render-ui')


def _GET_ONCE(resource, headers):
    url = URL + resource
    r = requests.get(url, headers)
    if r.status_code == 401:
        scope = r.json()['errors'][0]['detail'][0]
        params = {
            'service': 'registry',
            'scope': '%s:%s:%s' % (
                scope['Type'], scope['Name'], scope['Action']),
        }
        r = requests.get('https://hub.foundries.io/token-auth/',
                         params=params, headers=headers)
        if r.status_code == 200:
            if headers is None:
                headers = {}
            else:
                # don't want to overwrite the global copy since we are running
                # this in multiple threads
                headers = headers.copy()
            headers['Authorization'] = 'bearer ' + r.json()['token']
            r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.json()


def _GET(resource, headers):
    fail_with = None
    for x in range(5):
        if x > 0:
            delay = x * 2
            log.warning('Unable to get: %s, retrying in %d seconds',
                        resource, delay)
            time.sleep(delay)
        try:
            r = _GET_ONCE(resource, headers)
            return r
        except Exception as e:
            fail_with = e
    raise fail_with


def image_tags(image, arch):
    tags = []
    data = _GET(
        '/v2/%s/tags/list' % image, headers={'OSF-TOKEN': secret('osftok')})
    for t in data['tags']:
        if t.endswith(arch):
            tags.append(t.split('-')[0])
    return tags


def git_log(gitrepo):
    output = subprocess.check_output(
        ['git', 'log', '--format=%h', '-100'], cwd=gitrepo)
    return output.decode().splitlines()


def main(repo, container, arch):
    tags = image_tags(container, arch)
    for sha in git_log(repo):
        if sha in tags:
            print(sha)
            return
    sys.exit('Unable to find match')


if __name__ == '__main__':
    main(*sys.argv)
