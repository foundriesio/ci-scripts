# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import os
import base64
import tarfile
import subprocess
import json
import hashlib
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

    def download_compose_app(self, app_uri, dest_dir, extract=True):
        app_layers = self.download_layers(app_uri, self.download_manifest(app_uri))
        compose_app_archive = app_layers[0]
        if extract:
            tar = tarfile.open(fileobj=BIO(compose_app_archive))
            tar.extractall(dest_dir)
        else:
            return compose_app_archive

    def pull_manifest(self, uri):
        registry_jwt_token = self.__get_registry_jwt_token(uri.repo, uri.app)
        manifest_url = '{}/v2/{}/{}/manifests/{}'.format(self.registry_url, uri.repo, uri.app, uri.digest)
        manifest_resp = http_get(manifest_url,
                                 headers={'authorization': 'bearer {}'.format(registry_jwt_token['token']),
                                          'accept': 'application/vnd.oci.image.manifest.v1+json'})
        rec_hash = hashlib.sha256(manifest_resp.content).hexdigest()
        if rec_hash != uri.hash:
            raise Exception("Incorrect manifest hash; expected: {}, received: {}".format(uri.hash, rec_hash))
        return manifest_resp.content

    def download_manifest(self, image_uri):
        uri = self.parse_image_uri(image_uri)
        return json.loads(self.pull_manifest(uri))

    def pull_layer(self, image_uri, layer_digest, token=None):
        if not token:
            registry_jwt_token = self.__get_registry_jwt_token(image_uri.repo, image_uri.app)
            token = registry_jwt_token['token']

        layer_url = '{}/v2/{}/{}/blobs/{}'.format(self.registry_url, image_uri.repo, image_uri.app, layer_digest)
        archive_resp = http_get(layer_url, headers={'authorization': 'bearer {}'.format(token)})
        layer_hash = layer_digest[len('sha256:'):]
        rec_hash = hashlib.sha256(archive_resp.content).hexdigest()
        if rec_hash != layer_hash:
            raise Exception("Incorrect layer blob hash; expected: {}, received: {}".format(layer_hash, rec_hash))

        return archive_resp.content

    def download_layers(self, image_uri, manifest=None):
        if not manifest:
            manifest = self.download_manifest(image_uri)

        uri = self.parse_image_uri(image_uri)
        registry_jwt_token = self.__get_registry_jwt_token(uri.repo, uri.app)

        layer_archives = []
        for layer in manifest['layers']:
            layer_archives.append(self.pull_layer(uri, layer['digest'], registry_jwt_token['token']))
        return layer_archives

    @staticmethod
    def parse_image_uri(image_uri):
        class URI:
            def __init__(self, uri_str: str):
                uri_parts = uri_str.split('@')
                self.host, self.repo, self.app = uri_parts[0].split('/')
                uri_digest = uri_parts[1]
                if not uri_digest.startswith('sha256:'):
                    raise Exception("Unsupported type of URI digest: {}".format(uri_digest))

                self.digest = uri_digest
                self.hash = uri_digest[len('sha256:'):]
        return URI(image_uri)

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
