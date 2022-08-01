import json
import os
from os.path import expanduser

from helpers import cmd, jobserv_get, status
from tag_manager import TagMgr


def compose_tagged_uri(factory: str, org_uri: str, build_num: str, latest_tag: str) -> str:
    uri = org_uri.replace(f"_{factory}_", f"/{factory}/")
    tag_pos = uri.rindex("-")
    uri = uri[:tag_pos] + ':' + uri[tag_pos + 1:]
    return uri


def publish_manifest_lists(project: str = "", build_num: str = "", ota_lite_tag: str = ""):
    if not project:
        project = os.environ["H_PROJECT"]
    if not build_num:
        build_num = os.environ["H_BUILD"]
    if not ota_lite_tag:
        ota_lite_tag = os.environ["OTA_LITE_TAG"]
    if project == "lmp":
        factory = "lmp"
    else:
        factory, _ = project.split("/")
    latest_tag = TagMgr(ota_lite_tag).tags[0][0]

    status("Publish manifest lists for containers")
    build = jobserv_get(f"/projects/{project}/builds/{build_num}/")["data"]["build"]

    tags = {}

    manifests_dir = expanduser("~/.docker/manifests")
    os.makedirs(manifests_dir, exist_ok=True)

    for run in build["runs"]:
        status(f" Looking for containers built by {run['name']}")
        run = jobserv_get(run["url"])["data"]["run"]
        needle = run["url"] + "manifests/"
        for a in run.get("artifacts"):
            if a.startswith(needle):
                _, container_name, _ = a.rsplit("/", 2)
                tags[container_name] = 1
                mf = jobserv_get(a)
                path = os.path.join(manifests_dir, a[len(needle):])
                try:
                    os.mkdir(os.path.dirname(path))
                except FileExistsError:
                    pass
                with open(path, "w") as f:
                    json.dump(mf, f)

    for tag in tags.keys():
        # docker manifest stores things locally in an odd way (hoping to be
        # file system friendly perhaps?). It takes a container reference like:
        #  hub.foundries.io/andy-corp/shellhttpd:215_d8f9e18
        # and converts the slashes in the path to underscores and the colon
        # for the tag to a dash. E.g:
        #  hub.foundries.io_andy-corp_shellhttpd-215_d8f9e18
        # this logic decodes that from disk so we can understand exactly
        # what we should publish:
        mfdir = os.path.join(manifests_dir, tag)
        names = os.listdir(mfdir)
        status(f" Creating tagged URI from {names}; original URI: {tag}, build number: {build_num}, latest tag: {latest_tag}")
        uri = compose_tagged_uri(factory, tag, build_num, latest_tag)
        status(f" Pushing manifest to {uri}")
        cmd("docker", "manifest", "push", uri)
