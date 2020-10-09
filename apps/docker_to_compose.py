# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import yaml
import os

from helpers import status


def normalize_keyvals(params: dict, prefix=''):
    """Handles two types of docker-app params:
       1) traditional. eg:
          key: val
          returns data as is
       2) docker app nested. eg:
          shellhttp:
            port: 80
          returns dict: {shell.httpd: 80}
    """
    normalized = {}
    for k, v in params.items():
        assert type(k) == str
        if type(v) == str:
            normalized[prefix + k] = v
        elif type(v) == int:
            normalized[prefix + k] = str(v)
        elif type(v) == dict:
            sub = normalize_keyvals(v, prefix + k + '.')
            normalized.update(sub)
        else:
            raise ValueError('Invalid parameter type for: %r' % v)
    return normalized


def convert_docker_app(path: str):
    """Take a .dockerapp file to directory format.
       The file format isn't supported by docker-app 0.8 and beyond. Just
       split a 3 sectioned yaml file into its pieces
    """
    with open(path) as f:
        _, compose, params = yaml.safe_load_all(f)
    if params is None:
        params = {}
    os.unlink(path)
    path, _ = os.path.splitext(path)
    try:
        # this directory might already exist. ie the user has:
        # shellhttpd.dockerapp
        # shellhttpd/Dockerfile...
        os.rename(path, path + '.orig')  # just move out of the way
    except FileNotFoundError:
        pass
    os.mkdir(path)
    # We need to try and convert docker-app style parameters to parameters
    # that are compatible with docker-compose
    params = normalize_keyvals(params)
    compose_str = yaml.dump(compose)
    for k, v in params.items():
        # there are two things we have to replace:
        # 1) Things with no defaults - ie ports: 8080:${PORT}
        #    We need to make this ${PORT-<default>} if we can
        compose_str = compose_str.replace('${%s}' % k, '${%s-%s}' % (k, v))
        # 2) Things that are nested - ie foo.bar=12
        #    We have to make this foo_bar so compose will accept it
        if '.' in k:
            safek = k.replace('.', '_')
            status('Replacing parameter "%s" with "%s" for compatibility' % (
                   k, safek))
            compose_str = compose_str.replace('${' + k, '${' + safek)
    with open(os.path.join(path, 'docker-compose.yml'), 'w') as f:
        f.write(compose_str)
    status('Converted docker-compose for %s\n' % compose_str)


def convert_docker_apps():
    """Loop through all the .dockerapp files in a directory and convert them
       to directory-based docker-compose.yml friendly representations.
    """
    for p in os.listdir():
        if not p.endswith('.dockerapp'):
            continue
        if os.path.isfile(p):
            status('Converting .dockerapp file for: ' + p)
            convert_docker_app(p)
