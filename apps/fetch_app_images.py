import argparse
import logging
import os
import subprocess

from apps.compose_apps import ComposeApps
from apps.apps_publisher import AppsPublisher
from helpers import status


def main(args):
    status("Fetching app images to the local docker engine store")

    publisher = AppsPublisher(args.factory, "", "")
    apps = ComposeApps(args.apps_root, quiet=True)
    publisher.tag(apps, args.tag)
    for app in apps:
        subprocess.check_call(["docker", "compose", "--project-directory", app.dir, "pull"])


def get_args():
    factory = os.environ.get("FACTORY")
    arch = os.environ.get("ARCH")
    parser = argparse.ArgumentParser("Pull app images into a local docker store")
    parser.add_argument("--factory", default=factory)
    parser.add_argument("--apps-root", default="./")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--arch", default=arch)
    args = parser.parse_args()
    return args


if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(module)s: %(message)s', level=logging.INFO)
    args = get_args()

    # FACTORY must be set so that expandvars above will work correctly for
    # service images like: hub.foundries.io/${FACTORY}/foo
    os.environ["FACTORY"] = args.factory
    main(args)

