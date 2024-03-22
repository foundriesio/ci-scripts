import os
import json
import logging
import tarfile
import subprocess
from io import BytesIO as BIO

from factory_client import FactoryClient
from apps.docker_registry_client import DockerRegistryClient
from apps.dockerd import DockerDaemon
from apps.compose_apps import ComposeApps

logger = logging.getLogger(__name__)


class TargetAppsFetcher:
    TargetFile = 'targets.json'
    AppsDir = 'apps'
    ImagesDir = 'images'

    def __init__(self, token, work_dir, factory=None, client='docker'):
        if factory:
            self._factory_client = FactoryClient(factory, token)
        self._registry_client = DockerRegistryClient(token, client=client)
        self._work_dir = work_dir
        self.target_apps = {}
        self.create_target_dir = True

    def target_dir(self, target_name):
        if self.create_target_dir:
            return os.path.join(self._work_dir, target_name)
        else:
            return os.path.join(self._work_dir)

    def target_file(self, target_name):
        return os.path.join(self.target_dir(target_name), self.TargetFile)

    def apps_dir(self, target_name):
        return os.path.join(self.target_dir(target_name), self.AppsDir)

    def images_dir(self, target_name):
        return os.path.join(self.target_dir(target_name), self.ImagesDir)

    def fetch_target(self, target: FactoryClient.Target, shortlist=None, force=False):
        self.target_apps.clear()
        self.fetch_target_apps(target, apps_shortlist=target.shortlist or shortlist, force=force)
        self.fetch_apps_images(force=force)

    def fetch_target_apps(self, target: FactoryClient.Target, apps_shortlist=None, force=False):
        self.target_apps[target] = self._fetch_apps(target, apps_shortlist=apps_shortlist, force=force)

    def fetch_apps_images(self, graphdriver='overlay2', force=False):
        self._registry_client.login()
        for target, apps in self.target_apps.items():
            if not os.path.exists(self.images_dir(target.name)) or force:
                self._download_apps_images(apps, self.images_dir(target.name), target.platform, graphdriver)
            else:
                logger.info('Target Apps\' images have been already fetched; Target: {}'.format(target.name))

    def get_target_apps_size(self, target: FactoryClient.Target) -> int:
        # in kilobytes (`du -sb` returns so called "apparent size", hence we use `du -sk` - get usage in kilobytes)
        apps_size_str = subprocess.check_output(['du', '-sk', self.target_dir(target.name)]).split()[0].decode(
            'utf-8')
        apps_size_b = int(apps_size_str) * 1024
        return apps_size_b

    @staticmethod
    def _download_apps_images(apps: ComposeApps, app_images_dir, platform, graphdriver='overlay2'):
        os.makedirs(app_images_dir, exist_ok=True)
        with DockerDaemon(app_images_dir, graphdriver) as dockerd:
            for app in apps:
                app.download_images(platform, dockerd.host)

    def _fetch_apps(self, target, apps_shortlist=None, force=False):
        for app_name, app_uri in target.apps():
            if apps_shortlist and app_name not in apps_shortlist:
                logger.info('{} is not in the shortlist, skipping it'.format(app_name))
                continue

            app_dir = os.path.join(self.apps_dir(target.name), app_name)
            if not os.path.exists(app_dir) or force:
                os.makedirs(app_dir, exist_ok=True)
                logger.info('Downloading App; Target: {}, App: {}, Uri: {} '.format(target.name, app_name, app_uri))
                self._registry_client.download_compose_app(app_uri, app_dir)
            else:
                logger.info('App has been already fetched; Target: {}, App: {}'.format(target.name, app_name))
        return ComposeApps(self.apps_dir(target.name))


class SkopeAppFetcher(TargetAppsFetcher):
    UriFile = 'uri'
    ManifestFile = 'manifest.json'
    ArchiveFileExt = '.tgz'
    BlobsDir = 'blobs'

    def __init__(self, token, work_dir, factory=None, create_target_dir=True):
        super().__init__(token, work_dir, factory, client='skopeo')
        self.create_target_dir = create_target_dir

    def blobs_dir(self, target_name):
        return os.path.join(self.target_dir(target_name), self.BlobsDir)

    def _fetch_apps(self, target, apps_shortlist=None, force=False):
        fetched_apps = []
        blobs_dir = os.path.join(self.blobs_dir(target.name), "sha256")
        os.makedirs(blobs_dir, exist_ok=True)
        for app_name, app_uri in target.apps():
            if apps_shortlist and app_name not in apps_shortlist:
                logger.info('{} is not in the shortlist, skipping it'.format(app_name))
                continue

            uri = DockerRegistryClient.parse_image_uri(app_uri)
            app_dir = os.path.join(self.apps_dir(target.name), app_name, uri.hash)
            if os.path.exists(app_dir) and not force:
                logger.info('App has been already fetched; Target: {}, App: {}'.format(target.name, app_name))
                continue

            logger.info('Fetching App; Target: {}, App: {}, URI: {}, dst dir {} '
                        .format(target.name, app_name, app_uri, app_dir))
            os.makedirs(app_dir, exist_ok=True)
            with open(os.path.join(app_dir, self.UriFile), 'w') as f:
                f.write(app_uri)

            manifest_data = self._registry_client.pull_manifest(uri)
            with open(os.path.join(app_dir, self.ManifestFile), 'wb') as f:
                f.write(manifest_data)

            # Store the app manifest in the blobs directory to simplify its fetching from the store
            with open(os.path.join(blobs_dir, uri.hash), 'wb') as f:
                f.write(manifest_data)

            manifest = json.loads(manifest_data)
            app_blob_digest = manifest['layers'][0]['digest']
            app_blob_hash = app_blob_digest[len('sha256:'):]
            app_blob = self._registry_client.pull_layer(uri, app_blob_digest)
            app_blob_file = os.path.join(app_dir, app_blob_hash + self.ArchiveFileExt)
            with open(app_blob_file, 'wb') as f:
                f.write(app_blob)
            # Store the app archive/blob in the blobs directory to simplify fetching
            with open(os.path.join(blobs_dir, app_blob_hash), 'wb') as f:
                f.write(app_blob)

            with tarfile.open(fileobj=BIO(app_blob)) as t:
                t.extract('docker-compose.yml', app_dir)

            # Download and store the layers' manifest that contains a list of all layers that app's images are based on.
            # It's needed for aklite to calculate an update size in an offline update case.
            for lm in manifest.get('manifests', []):
                if target.platform == lm['platform']['architecture']:
                    lm_uri = self._registry_client.parse_image_uri(uri.host + '/' + uri.name + "@" + lm["digest"])
                    layers_index = self._registry_client.pull_manifest(lm_uri, 'application/vnd.oci.image.index.v1+json')
                    with open(os.path.join(blobs_dir, lm_uri.hash), 'wb') as f:
                        f.write(layers_index)

            # If present, then download and store the app layers metadata that contains precise
            # sizes of extracted layers.
            # The metadata are used to calculate exact update size during offline update
            if len(manifest.get('layers', [])) > 1 and \
                    manifest['layers'][1].get('annotations', {}).get('layers-meta') == 'v1':
                layer_desc = manifest['layers'][1]
                blob = self._registry_client.pull_layer(uri, layer_desc['digest'])
                blob_file = os.path.join(blobs_dir, layer_desc['digest'][len('sha256:'):])
                with open(blob_file, 'wb') as f:
                    f.write(blob)

            fetched_apps.append(ComposeApps.App(app_name, app_dir))
        return fetched_apps

    def fetch_apps_images(self, graphdriver='overlay2', force=False):
        self._registry_client.login()
        for target, apps in self.target_apps.items():
            logger.info('Pulling images of {} apps'.format(target.name))
            for app in apps:
                logger.info('Pulling {} images'.format(app.name))
                images_dir = os.path.join(app.dir, self.ImagesDir)
                os.makedirs(images_dir, exist_ok=True)
                for image in app.images():
                    self.fetch_image(target.name, target.platform, image, images_dir)

    def fetch_image(self, target_name: str, arch: str, image: str, dst_root_dir: str):
        logger.info('Pulling image: {}'.format(image))
        uri = self._registry_client.parse_image_uri(image)
        image_dir = os.path.join(dst_root_dir, uri.host, uri.name, uri.hash)
        os.makedirs(image_dir, exist_ok=True)
        subprocess.check_call(['skopeo', '--insecure-policy', '--override-arch', arch, 'copy',
                               '--retry-times', '3', '--format', 'v2s2', '--dest-shared-blob-dir',
                               self.blobs_dir(target_name), 'docker://' + image, 'oci:' + image_dir])

        # Store the image manifest in the blob directory, as result it contains all blobs/nodes of
        # the app's merkle tree. It allows to check app integrity on devices with preloaded apps and
        # in the case of offline update.
        # Note: the skopeo is supposed to store it, no idea why they don't do it
        blob = subprocess.check_output(['skopeo', 'inspect', '--raw', f'docker://{image}'])
        with open(os.path.join(self.blobs_dir(target_name), "sha256", uri.hash), 'wb') as f:
            f.write(blob)
