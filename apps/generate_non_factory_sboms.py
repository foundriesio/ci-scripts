import argparse
import logging
import os
import subprocess

from apps.compose_apps import ComposeApps
from helpers import status


def main(args):
    status("Loading docker-compose files to find non-factory containers")
    factory_prefix = f"hub.foundries.io/{args.factory}/"

    apps = ComposeApps(args.apps_root, quiet=True)
    analyzed = {}
    for app in apps:
        for img in app.images(expand_env=True):
            if not img.startswith(factory_prefix) and img not in analyzed:
                status(f"Doing a syft SBOM scan for {img}")
                analyzed[img] = 1
                path = os.path.join(args.archive, img, f"{args.arch}.spdx.json")
                os.makedirs(os.path.dirname(path), exist_ok=True)
                try:
                    # Syft doesn't know how to determine the platform correctly.
                    # This causes problems for some 32-bit arm images. Images
                    # such as eclipse-mosquitto only build for arm/v6. If
                    # we ask for arm or arm/v7 - sfyt will fail. However,
                    # dockerd is smart enough to get the "best" arm image
                    # available for a given architecure.
                    subprocess.check_call(["docker", "pull", img])
                    out = subprocess.check_output(["syft", "docker:" + img, "-o", "spdx-json"])
                    with open(path, "wb") as f:
                        f.write(out)
                except Exception:
                    status("Unable to scan the image for this platform")


def get_args():
    factory = os.environ.get("FACTORY")
    arch = os.environ.get("ARCH")
    parser = argparse.ArgumentParser(
        "Generate SBOMs from non-factory containers defined in compose apps.")
    parser.add_argument("--arch", default=arch)
    parser.add_argument("--factory", default=factory)
    parser.add_argument("--apps-root", default="./")
    parser.add_argument("--archive", default="/archive/sboms")
    args = parser.parse_args()
    return args


if __name__ == "__main__":
    logging.basicConfig(format='%(asctime)s %(levelname)s: %(module)s: %(message)s', level=logging.INFO)
    args = get_args()

    # FACTORY must be set so that expandvars above will work correctly for
    # service images like: hub.foundries.io/${FACTORY}/foo
    os.environ["FACTORY"] = args.factory
    main(args)

