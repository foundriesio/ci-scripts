# Copyright (c) 2020 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import os
import subprocess
import shutil
import logging
import tempfile

from factory_client import FactoryClient


logger = logging.getLogger("Target Apps Store")


class TargetAppsStore:
    def __init__(self):
        pass

    def store(self, target: FactoryClient.Target, images_dir: str):
        pass

    def exist(self, target: FactoryClient.Target):
        pass

    def images_size(self, target: FactoryClient.Target):
        pass

    def copy(self, target: FactoryClient.Target, dst_images_dir: str, dst_apps_dir: str):
        pass

    def apps_location(self, target: FactoryClient.Target):
        pass

EXTRACTION_SCRIPT = '''#!/bin/sh
set -e
set -o pipefail
if [ $# -ne 1 ] ; then
    echo "Usage: $0 <decryption key>"
    exit 1
fi

archive=$(grep --text --line-number '# ARCHIVE:$' $0 | cut -d: -f1)
cp /var/lib/docker/image/overlay2/repositories.json /tmp/orig.json
echo "Extracting container images"
tail -n +$((archive + 1)) $0 | openssl enc -pbkdf2 -d -aes256 -k $1 \\
    | tar -C /var/lib/docker --strip-components=2 -x ./images

python3 -c 'import json; cur = json.load(open("/tmp/orig.json")); new = json.load(open("/var/lib/docker/image/overlay2/repositories.json")); cur["Repositories"].update(new["Repositories"]); json.dump(cur, open("/var/lib/docker/image/overlay2/repositories.json", "w"))'

echo "Extracting compose apps"
tail -n +$((archive + 1)) $0 | openssl enc -pbkdf2 -d -aes256 -k $1 \\
    | tar -C /var/sota/compose-apps --strip-components=2 -x ./apps

rm $0

systemctl restart docker

exit 0

# ARCHIVE:
'''

class ArchiveTargetAppsStore(TargetAppsStore):
    def __init__(self, root_dir):
        self._root_dir = root_dir

    def store(self, target: FactoryClient.Target, images_dir: str):
        arch_dir, app_image_tar, app_image_size_file = self.apps_location(target)
        os.makedirs(arch_dir, exist_ok=True)
        subprocess.check_call(['tar', '-cf', app_image_tar, '-C', images_dir, '.'])
        image_data_size = subprocess.check_output(['du', '-sk', images_dir]).split()[0].decode('utf-8')
        with open(app_image_size_file, 'w') as f:
            f.write(image_data_size)

    def exist(self, target: FactoryClient.Target, just_images=False):
        result = False
        try:
            _, app_image_tar, _ = self.apps_location(target, just_images)
            result = os.path.exists(app_image_tar)
        except Exception as exc:
            logger.warning('Failed to get Target Apps images location; Target: {}, error: {}'.
                           format(target.name, exc))

        return result

    def images_size(self, target: FactoryClient.Target):
        try:
            _, app_image_tar, app_image_size_file = self.apps_location(target)
            if not os.path.exists(app_image_size_file):
                app_image_size = self.__get_images_size(target)
            else:
                with open(app_image_size_file, 'r') as f:
                    app_image_size = int(f.readline())
        except Exception as exc:
            logger.warning('Failed to obtain apps images size: {}'.format(exc))
            app_image_size = round(os.path.getsize(app_image_tar) / 1024, 3)

        return app_image_size

    def _copy_encrypted(self, app_img: str, dst_images_dir: str, encryption_key: str):
        path = os.path.join(dst_images_dir, 'extract-encrypted-apps')
        logger.info('Creating self extracting encrypted file: %s', path)
        with open(path, 'wb') as f:
            os.fchmod(f.fileno(), 0o755)
            f.write(EXTRACTION_SCRIPT.encode())
            f.flush()
            subprocess.check_call(['openssl', 'enc', '-pbkdf2', '-e', '-aes256',
                                   '-in', app_img, '-k', encryption_key], stdout=f)

    def copy(self, target: FactoryClient.Target, dst_images_dir: str, dst_apps_dir: str):
        if not self.exist(target):
            # Try to find an archive file that contains just images
            if self.exist(target, just_images=True):
                logger.info('Copying only Apps\' container images...')
                return self._copy_images(target, dst_images_dir)
            else:
                raise Exception('Failed to find images of the given Target {}'.format(target.name))

        _, app_image_tar, _ = self.apps_location(target)
        if target.app_encrypted_key:
            return self._copy_encrypted(app_image_tar, dst_images_dir, target.app_encrypted_key)

        if os.path.exists(dst_images_dir):
            # wic image was populated by container images data during LmP build
            # let's remove it and populate with the given images data
            logger.info('Removing existing preloaded app images from the system image')
            shutil.rmtree(dst_images_dir)

        os.makedirs(dst_images_dir)
        logger.info('Copying container images of Target Apps; Target: {}, Source: {}, Destination: {}'
                    .format(target.name, app_image_tar, dst_images_dir))
        subprocess.check_call(['tar', '--strip-components=2', '-xf', app_image_tar, '-C', dst_images_dir, './images'])

        if dst_apps_dir is None:
            logger.info('Destination compose apps root dir is not specified, skipping Apps copying')
            return

        if os.path.exists(dst_apps_dir):
            # wic image was populated by container images data during LmP build
            # let's remove it and populate with the given images data
            logger.info('Removing existing preloaded compose apps from the system image')
            shutil.rmtree(dst_apps_dir)

        os.makedirs(dst_apps_dir)
        logger.info('Copying Target Apps; Target: {}, Source: {}, Destination: {}'
                    .format(target.name, app_image_tar, dst_apps_dir))
        subprocess.check_call(['tar', '--strip-components=2', '-xf', app_image_tar, '-C', dst_apps_dir,  './apps'])

    def apps_location(self, target: FactoryClient.Target, just_images=False):
        arch_dir = os.path.join(self._root_dir, target.sha)
        if target.shortlist:
            target_apps_file_basename = '{}-{}-{}'.format(target.sha, target.platform, '-'.join(target.shortlist))
        else:
            target_apps_file_basename = '{}-{}'.format(target.sha, target.platform)

        if not just_images:
            target_apps_file_basename = 'apps-' + target_apps_file_basename

        app_image_tar = os.path.join(arch_dir, '{}.tar'.format(target_apps_file_basename))
        app_image_size_file = os.path.join(arch_dir, '{}.size'.format(target_apps_file_basename))
        return arch_dir, app_image_tar, app_image_size_file

    def __get_images_size(self, target: FactoryClient.Target):
        _, app_image_tar, app_image_size_file = self.apps_location(target)
        with tempfile.TemporaryDirectory() as tmp_image_data:
            subprocess.check_call(['tar', '-xf', app_image_tar, '-C', tmp_image_data])
            image_data_size = subprocess.check_output(['du', '-sk', tmp_image_data]).split()[0].decode('utf-8')
            with open(app_image_size_file, 'w') as f:
                f.write(image_data_size)
            return int(image_data_size)

    def _copy_images(self, target: FactoryClient.Target, dst_dir: str):
        _, app_image_tar, _ = self.apps_location(target, just_images=True)

        if os.path.exists(dst_dir):
            # wic image was populated by container images data during LmP build
            # let's remove it and populate with the given images data
            logger.info('Removing existing preloaded app images from the system image')
            shutil.rmtree(dst_dir)

        os.makedirs(dst_dir)
        logger.info('Copying container images of Target Apps; Target: {}, Source: {}, Destination: {}'
                    .format(target.name, app_image_tar, dst_dir))
        subprocess.check_call(['tar', '-xf', app_image_tar, '-C', dst_dir])
