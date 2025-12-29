# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: BSD-3-Clause

import os
import sys
import base64
import tarfile
import subprocess
import json
import hashlib
import requests
from io import BytesIO as BIO
from pathlib import Path

from helpers import fio_dnsbase, http_get, status


class DockerRegistryClient:
    DefaultRegistryHost = 'hub.' + fio_dnsbase()

    def __init__(self, token: str, registry_host=DefaultRegistryHost, schema='https', client='docker'):
        self._token = token
        self.registry_url = '{}://{}'.format(schema, registry_host)
        self.registry_host = registry_host
        self._client = client

        self._jwt_token = None

    def download_compose_app(self, app_uri, dest_dir, extract=True):
        app_layers = self.download_layers(app_uri, self.download_manifest(app_uri))
        compose_app_archive = app_layers[0]
        if extract:
            tar = tarfile.open(fileobj=BIO(compose_app_archive))
            tar.extractall(dest_dir)
        else:
            return compose_app_archive

    def pull_manifest(self, uri, format='application/vnd.oci.image.manifest.v1+json'):
        manifest_url = '{}/v2/{}/manifests/{}'.format(self.registry_url, uri.name, uri.digest)
        req_headers = {'accept': format}
        if uri.factory:
            registry_jwt_token = self.__get_registry_jwt_token(manifest_url)
            req_headers['authorization'] = 'bearer {}'.format(registry_jwt_token['token'])

        manifest_resp = http_get(manifest_url, headers=req_headers)
        rec_hash = hashlib.sha256(manifest_resp.content).hexdigest()
        if rec_hash != uri.hash:
            raise Exception("Incorrect manifest hash; expected: {}, received: {}".format(uri.hash, rec_hash))
        return manifest_resp.content

    def download_manifest(self, image_uri):
        uri = self.parse_image_uri(image_uri)
        return json.loads(self.pull_manifest(uri))

    def pull_layer(self, image_uri, layer_digest, token=None):
        layer_url = '{}/v2/{}/blobs/{}'.format(self.registry_url, image_uri.name, layer_digest)

        if not token and image_uri.factory:
            registry_jwt_token = self.__get_registry_jwt_token(layer_url)
            token = registry_jwt_token['token']

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
        token = None
        if uri.factory:
            layer_url = '{}/v2/{}/blobs/{}'.format(self.registry_url, uri.name,
                                                   manifest['layers'][0]['digest'])
            registry_jwt_token = self.__get_registry_jwt_token(layer_url)
            token = registry_jwt_token['token']

        layer_archives = []
        for layer in manifest['layers']:
            layer_archives.append(self.pull_layer(uri, layer['digest'], token))
        return layer_archives

    @staticmethod
    def parse_image_uri(image_uri):
        class URI:
            def __init__(self, uri_str: str):
                uri_parts = uri_str.split('@')
                if len(uri_parts) != 2:
                    raise ValueError("Invalid image URI, a digest delimiter is not found: ", uri_str)

                host_end_indx = uri_parts[0].find('/')
                if -1 == host_end_indx:
                    raise ValueError("Invalid image URI, hostname and path delimiter is not found digest: {}"
                                    .format(uri_str))
                self.host = uri_parts[0][:host_end_indx]

                self.name = uri_parts[0][host_end_indx + 1:]
                if len(self.name) == 0:
                    raise ValueError("Invalid image URI, an image name/path is empty: {}".format(uri_str))

                uri_digest = uri_parts[1]
                if not uri_digest.startswith('sha256:'):
                    raise ValueError("Unsupported type of URI digest: {}".format(uri_digest))
                self.digest = uri_digest
                self.hash = uri_digest[len('sha256:'):]

                if self.host == DockerRegistryClient.DefaultRegistryHost:
                    self.factory, self.app = self.name.split('/')
                else:
                    self.factory = None
                    self.app = None

        return URI(image_uri)

    def __get_registry_jwt_token(self, uri):
        r = requests.get(uri)
        if r.status_code != 401:
            raise Exception('No expected status code `401` is received;'
                            f' uri: {uri}, code: {r.status_code}, status: {r.text}')

        auth_header = r.headers.get("www-authenticate")
        if not auth_header:
            raise Exception('No expected auth header `www-authenticate` is received;'
                            f' uri: {uri}, code: {r.status_code}, status: {r.text}')

        auth_header = auth_header.lower()
        auth_type = 'bearer'
        if not auth_header.startswith(auth_type):
            raise Exception('Unexpected auth header `www-authenticate` value;'
                            f' uri: {uri}, www-authenticate: {auth_header},  expected: {auth_type}')

        auth_header_value = auth_header[len(auth_type):].strip()
        auth_params = {}
        for p in auth_header_value.split(','):
            k, v = p.split('=')
            auth_params[k.strip()] = v.strip().strip('"')

        auth_endpoint = auth_params.get('realm')
        if not auth_endpoint:
            raise Exception('No `realm` is found in `www-authenticate` value;'
                            f' uri: {uri}, www-authenticate: {auth_header}')

        del auth_params['realm']

        user_pass = '{}:{}'.format('ci-script-client', self._token)
        headers = {'Authorization': 'Basic ' + base64.b64encode(user_pass.encode()).decode()}

        token_req = http_get(auth_endpoint, headers=headers, params=auth_params)
        return token_req.json()

    def login(self):
        login_process = subprocess.Popen(
            [self._client, 'login', self.registry_host, '--username=doesntmatter', '--password-stdin'],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

        output = login_process.communicate(input=self._token.encode())[0]
        # this is kind of useless verification because login at hub.foundries.io is successful
        # for any value of username and/or password
        if -1 == (str(output)).find('Login Succeeded'):
            raise Exception(f'Failed to login at {self.registry_host}')


# TODO: Refactor this implementation, subclass for each Registry type, and inheritance from DockerRegistryClient
class ThirdPartyRegistry:
    def __init__(self, registries_creds, client='docker'):
        self._registries_creds = registries_creds
        self._client = client

    def login(self):
        for reg in self._registries_creds:
            url = reg.get("url")
            if url:
                status("Configuring registry %s - %s" % (reg["type"], url))
            else:
                status("Configuring registry %s" % reg["type"])
            if reg["type"] == "aws":
                creds_file = Path.home() / ".aws/credentials"
                creds_file.parent.mkdir()
                secrets_file = Path("/secrets") / reg["aws_creds_secret_name"]
                creds_file.write_text(secrets_file.read_text())

                try:
                    cmd = ["aws", "ecr", "get-login-password", "--region", reg["region"]]
                    token = subprocess.check_output(cmd)
                    cmd = [self._client, "login", "--password-stdin", "-u", "AWS", reg["url"]]
                    subprocess.run(cmd, check=True, input=token)
                except subprocess.CalledProcessError as e:
                    sys.exit(e.returncode)
            elif reg["type"] == "azure":
                secrets_file = Path("/secrets") / reg["azure_principal_secret_name"]
                creds = secrets_file.read_text().strip()
                user, token = creds.split(":")
                try:
                    cmd = [self._client, "login", "--password-stdin", "-u", user, reg["url"]]
                    subprocess.run(cmd, check=True, input=token.encode())
                except subprocess.CalledProcessError as e:
                    sys.exit(e.returncode)
            elif reg["type"] == "gar":
                creds_file = Path.home() / ".config/gcloud/application_default_credentials.json"
                creds_file.parent.mkdir(parents=True)
                secrets_file = Path("/secrets") / reg["gar_creds_secret_name"]
                creds_file.write_text(secrets_file.read_text())
                try:
                    cmd = ["docker-credential-gcr", "configure-docker", "--include-artifact-registry"]
                    subprocess.run(cmd, check=True)
                except subprocess.CalledProcessError as e:
                    sys.exit(e.returncode)
            elif reg["type"] == "generic":
                secrets_file = Path("/secrets") / reg["generic_secret_name"]
                creds = secrets_file.read_text().strip()
                user, token = creds.split(":")
                try:
                    cmd = [self._client, "login", "--password-stdin", "-u", user, reg["url"]]
                    subprocess.run(cmd, check=True, input=token.encode())
                except subprocess.CalledProcessError as e:
                    sys.exit(e.returncode)
            else:
                sys.exit("Unsupported registry type")
