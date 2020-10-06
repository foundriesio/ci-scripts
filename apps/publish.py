#!/usr/bin/python3
#
# Copyright (c) 2019 Foundries.io
# SPDX-License-Identifier: Apache-2.0

import logging
import argparse


from helpers import status
from apps.target_manager import create_target
from apps.compose_apps import ComposeApps

logging.basicConfig(level='INFO')


# def publish(factory: str, apps_version: str, app_name: str, publish_tool: str) -> str:
#     base = 'hub.foundries.io/' + factory + '/'
#     app = base + app_name
#     tagged = app + ':app-' + apps_version
#
#     changed = False
#     with open(os.path.join(app_name, 'docker-compose.yml')) as f:
#         compose = yaml.safe_load(f)
#         for name, svc in compose['services'].items():
#             img = svc['image']
#             if img.startswith(base):
#                 # this should be a container defined in this factory and
#                 # in its containers.git, so it should get pinned to ${TAG}
#                 # to work as expected
#                 parts = img.split(':')
#                 if len(parts) == 1:
#                     status('Image pinned to latest: %s, updating to %s' % (
#                         img, apps_version))
#                     svc['image'] = img + ':' + apps_version
#                     changed = True
#                 elif len(parts) == 2:
#                     allowed = ['${TAG}', 'latest', apps_version]
#                     if factory == 'lmp':
#                         # the lmp containers repo pulls in fiotest which sets
#                         # its tag to "postmerge" which is okay based on how
#                         # we do tagging for that repo.
#                         allowed.append('postmerge')
#                     if parts[1] not in allowed:
#                         sys.exit('Image pinned to %s should be ${TAG} or %s' % (
#                             parts[1], apps_version))
#                     svc['image'] = parts[0] + ':' + apps_version
#                     changed = True
#                 else:
#                     sys.exit('Unexpected image value: ' + img)
#     if changed:
#         with open(os.path.join(app_name, 'docker-compose.yml'), 'w') as f:
#             yaml.dump(compose, f)
#
#     out = cmd(publish_tool, tagged, cwd=app_name, capture=True)
#     # The publish command produces output like:
#     # = Publishing app...
#     # |-> app:  sha256:fc73321368c7a805b0f697a0a845470bc022b6bdd45a8b34
#     # |-> manifest:  sha256:e15e3824fc21ce13815aecb0490d60b3a32
#     # We need the manifest sha so we can pin it properly in targets.json
#     needle = b'|-> manifest:  sha256:'
#     sha = out[out.find(needle) + len(needle):].strip()
#     return app + '@sha256:' + sha.decode()


def main(factory: str, sha: str, targets_json: str, app_root_dir: str, publish_tool: str, apps_version: str,
         target_tag: str, target_version: str):
    apps_to_add_to_target = {}

    status('Searching for Compose Apps in {}'.format(app_root_dir))
    apps = ComposeApps(app_root_dir)
    status('Found Compose Apps: {}'.format(len(apps)))

    status('Validating Compose Apps')
    apps.validate()
    status('Compose Apps has been validated: {}'.format(apps.str))

    status('Tagging Apps...')
    allowed_tags = ['${TAG}', 'latest']
    if factory == 'lmp':
    # the lmp containers repo pulls in fiotest which sets
                            # its tag to "postmerge" which is okay based on how
                            # we do tagging for that repo.
                            allowed_tags.append('postmerge')
    for app in apps:
        status('Tagging: ' + app.name)
        app.tag_images(apps_version, 'hub.foundries.io/{}'.format(factory), allowed_tags)

    status('Publishing Apps...')
    for app in apps:
        status('Publishing: ' + app.name)
        tagged = 'hub.foundries.io/' + factory + '/' + app.name + ':app-' + apps_version
        sha = app.publish(publish_tool, tagged)
        uri = 'hub.foundries.io/' + factory + '/' + app.name + '@sha256:' + sha
        apps_to_add_to_target[app.name] = {'uri': uri}

    status('Creating Target(s) that refers to the published Apps; tag: {}, version: {} '
           .format(target_tag, target_version))
    res = create_target(targets_json, apps_to_add_to_target, target_tag, sha, target_version)
    if not res:
        logging.error('Failed to create Targets for the published Apps')
    return res


def get_args():
    parser = argparse.ArgumentParser('''Publish Target Compose Apps''')
    parser.add_argument('-f', '--factory', help='Apps Factory')
    parser.add_argument('-t', '--targets', help='Targets json file')
    parser.add_argument('-d', '--apps-root-dir', help='Compose Apps root directory')
    parser.add_argument('-p', '--publish-tool', help='A utility to be used for publishing (compose-ref)')
    parser.add_argument('-v', '--apps-version', help='Apps version which is by default is an abbreviated commit hash'
                                                     'of a given containers.git repo')
    parser.add_argument('-tt', '--target-tag', help='A tag to apply to Targets that will be created'
                                                    'by publishing the given apps')
    parser.add_argument('-s', '--git-sha', help='App/containers repo git sha')
    parser.add_argument('-tv', '--target-version', help='Version of Targets that will be created by a given call',
                        required=False, default=None)

    args = parser.parse_args()
    return args


if __name__ == '__main__':
    args = get_args()
    res = main(args.factory, args.git_sha, args.targets, args.apps_root_dir, args.publish_tool,
               args.apps_version, args.target_tag, args.target_version)

    exit(0 if res else 1)
