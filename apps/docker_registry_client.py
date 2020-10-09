# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import os
import base64
import tarfile
import subprocess
import json
try:
    from cStringIO import StringIO as BIO
except ImportError: # python 3
    from io import BytesIO as BIO

from helpers import http_get


class DockerRegistryClient:
    DefaultRegistryHost = 'hub.foundries.io'

    def __init__(self, token: str, registry_host=DefaultRegistryHost, schema='https'):
        self._token = token
        self.registry_url = '{}://{}'.format(schema, registry_host)
        self.registry_host = registry_host
        self.auth_endpoint = os.path.join(self.registry_url, 'token-auth/')

        self._jwt_token = None

    def download_compose_app(self, app_uri, dest_dir):
        app_layers = self.download_layers(app_uri, self.download_manifest(app_uri))
        compose_app_archive = app_layers[0]
        tar = tarfile.open(fileobj=BIO(compose_app_archive))
        tar.extractall(dest_dir)

    def download_manifest(self, image_uri):
        repo, app, digest = self.parse_image_uri(image_uri)
        registry_jwt_token = self.__get_registry_jwt_token(repo, app)
        manifest_url = '{}/v2/{}/{}/manifests/{}'.format(self.registry_url, repo, app, digest)
        manifest_resp = http_get(manifest_url,
                                 headers={'authorization': 'bearer {}'.format(registry_jwt_token['token']),
                                          'accept': 'application/vnd.oci.image.manifest.v1+json'})
        return json.loads(manifest_resp.content)

    def download_layers(self, image_uri, manifest=None):
        if not manifest:
            manifest = self.download_manifest(image_uri)

        repo, app, digest = self.parse_image_uri(image_uri)
        registry_jwt_token = self.__get_registry_jwt_token(repo, app)

        layer_archives = []
        for layer in manifest['layers']:
            layer_url = '{}/v2/{}/{}/blobs/{}'.format(self.registry_url, repo, app, layer['digest'])
            archive_resp = http_get(layer_url, headers={'authorization': 'bearer {}'.format(registry_jwt_token['token'])})
            layer_archives.append(archive_resp.content)
        return layer_archives

    @staticmethod
    def parse_image_uri(image_uri):
        uri_parts = image_uri.split('@')
        registry_host, repo, app = uri_parts[0].split('/')
        digest = uri_parts[1]
        return repo, app, digest

    def __get_registry_jwt_token(self, repo, app):
        user_pass = '{}:{}'.format('ci-script-client', self._token)
        headers = {'Authorization': 'Basic ' + base64.b64encode(user_pass.encode()).decode()}

        params = {
            'service': 'registry',
            'scope': 'repository:{}/{}:pull'.format(repo, app)
        }

        token_req = http_get(self.auth_endpoint, headers=headers, params=params)
        return token_req.json()

    def login(self):
        login_process = subprocess.Popen(
            ['docker', 'login', self.registry_host, '--username=doesntmatter', '--password-stdin'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        output = login_process.communicate(input=self._token.encode())[0]
        # this is kind of useless verification because login at hub.foundries.io is successful
        # for any value of username and/or password
        if -1 == (str(output)).find('Login Succeeded'):
            raise Exception('Failed to login at {}'.format('hub.foundries.io'))
