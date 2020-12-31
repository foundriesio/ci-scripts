import os
import json
import logging

from factory_client import FactoryClient
from apps.docker_registry_client import DockerRegistryClient
from apps.dockerd import DockerDaemon
from apps.compose_apps import ComposeApps

logger = logging.getLogger(__name__)


class TargetAppsFetcher:
    TargetFile = 'targets.json'
    AppsDir = 'apps'
    ImagesDir = 'images'

    def __init__(self, token, work_dir, factory=None):
        if factory:
            self._factory_client = FactoryClient(factory, token)
        self._registry_client = DockerRegistryClient(token)
        self._work_dir = work_dir
        self.target_apps = {}

    def target_dir(self, target_name):
        return os.path.join(self._work_dir, target_name)

    def target_file(self, target_name):
        return os.path.join(self.target_dir(target_name), self.TargetFile)

    def apps_dir(self, target_name):
        return os.path.join(self.target_dir(target_name), self.AppsDir)

    def images_dir(self, target_name):
        return os.path.join(self.target_dir(target_name), self.ImagesDir)

    def fetch_target(self, target: FactoryClient.Target, force=False):
        self.target_apps.clear()
        self.fetch_target_apps(target, apps_shortlist=target.shortlist, force=force)
        self.fetch_apps_images(force=force)

    def fetch_target_apps(self, target: FactoryClient.Target, apps_shortlist=None, force=False):
        self.target_apps[target] = self._fetch_apps(target, apps_shortlist=apps_shortlist, force=force)

    def fetch_apps(self, targets: dict):
        for target_name, target_json in targets.items():
            target = FactoryClient.Target(target_name, target_json)
            self.target_apps[target] = self._fetch_apps(target)

    def fetch_apps_images(self, graphdriver='overlay2', force=False):
        self._registry_client.login()
        for target, apps in self.target_apps.items():
            if not os.path.exists(self.images_dir(target.name)) or force:
                self._download_apps_images(apps, self.images_dir(target.name), target.platform, graphdriver)
            else:
                logger.info('Target Apps\' images have been already fetched; Target: {}'.format(target.name))

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
