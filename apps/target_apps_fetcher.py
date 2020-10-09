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

    def fetch_target_apps(self, target: FactoryClient.Target, apps_shortlist=None):
        self.target_apps[target] = self.__fetch_apps(target.name, apps_shortlist, target)

    def fetch_apps(self, targets: dict):
        for target_name, target_json in targets.items():
            target = FactoryClient.Target(target_name, target_json)
            self.target_apps[target] = self.__fetch_apps(target_name, target=target)

    def fetch_apps_images(self, graphdriver='overlay2'):
        self._registry_client.login()
        for target, apps in self.target_apps.items():
            if not os.path.exists(self.images_dir(target.name)):
                self.__download_apps_images(apps, self.images_dir(target.name), target.platform, graphdriver)

    @staticmethod
    def __download_apps_images(apps: ComposeApps, app_images_dir, platform, graphdriver='overlay2'):
        os.makedirs(app_images_dir, exist_ok=True)
        with DockerDaemon(app_images_dir, graphdriver) as dockerd:
            for app in apps:
                app.download_images(platform, dockerd.host)

    def __fetch_apps(self, target_name, apps_shortlist=None, target=None):
        if not target:
            target = self.__fetch_target(target_name)

        for app_name, app_uri in target.apps():
            if apps_shortlist and app_name not in apps_shortlist:
                logger.info('{} is not in the shortlist, skipping it'.format(app_name))
                continue

            app_dir = os.path.join(self.apps_dir(target_name), app_name)
            if not os.path.exists(app_dir):
                os.makedirs(app_dir, exist_ok=True)
                logger.info('Downloading App; Target: {}, App: {}, Uri: {} '.format(target_name, app_name, app_uri))
                self._registry_client.download_compose_app(app_uri, app_dir)
        return ComposeApps(self.apps_dir(target_name))

    def __fetch_target(self, target_name):
        logger.info('Downloading Target: {} '.format(target_name))
        if not os.path.exists(self.target_file(target_name)):
            target = self._factory_client.get_target(target_name)
            os.makedirs(self.target_dir(target_name), exist_ok=True)
            with open(self.target_file(target_name), "w") as ff:
                json.dump(target.target_json, ff)
        else:
            with open(self.target_file(target_name), "r") as ff:
                target = FactoryClient.Target(json.load(ff))
        return target
