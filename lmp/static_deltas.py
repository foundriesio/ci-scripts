import os
import hashlib
import canonicaljson
import requests
from typing import List, NamedTuple, Tuple

from helpers import (
    Progress,
    cmd,
    status,
    secret
)


class Delta(NamedTuple):
    to: Tuple[str, str]  # (hash, uri)
    froms: List[Tuple[str, str]]


def generate_deltas(prog: Progress, deltas: List[Delta], repo: str) -> dict:
    delta_stats = {}
    for (to_sha, _), from_list in deltas:
        delta_stat = {to_sha: {}}  # delta stats for a single `to` and many `from`
        for from_sha, _ in from_list:
            cmd("ostree", "static-delta",
                "generate", f"--repo={repo}", "--from", from_sha, "--to", to_sha)

            # Get delta stats for the given `from`
            delta_stat[to_sha][from_sha] = _get_delta_stats(repo, from_sha, to_sha)
            prog.tick()

        delta_stat_json = canonicaljson.encode_canonical_json(delta_stat)
        delta_stat_json_sha = hashlib.sha256()
        delta_stat_json_sha.update(delta_stat_json)
        delta_stats[to_sha] = {
            "sha256": delta_stat_json_sha.hexdigest(),
            "canonical-json": delta_stat_json
        }
    return delta_stats


# The delta stats are saved as a canonical json; a file name matches a `to` hash. Format is:
# {
#   "to-hash": {
#       "from-hash": { "size": <compressed delta size>, "u_size": <unpacked delta size>}
#       ...
#    }
# }
def save_delta_stats(delta_stats: dict, out_dir: str):
    for to_sha, s in delta_stats.items():
        with open(os.path.join(out_dir, f"{to_sha}.json"), "wb") as f:
            f.write(s["canonical-json"])


def upload_delta_stats(factory: str, delta_stats: dict, tok_secret_name: str):
    ostreehub_uri = f"https://api.foundries.io/ota/ostreehub/{factory}/v2/repos/lmp/delta-stats"
    for to_sha, s in delta_stats.items():
        status(f"Uploading delta stats for {to_sha}...")
        r = requests.put(ostreehub_uri,
                         headers={
                             "osf-token": secret(tok_secret_name),
                             "content-type": "application/json",
                             "content-digest": f"sha-256=:{s['sha256']}:"
                         },
                         data=s["canonical-json"])
        if not r.ok:
            raise requests.exceptions.HTTPError("Failed to upload delta stats to ostreehub; "
                                                f"{r.status_code}, err: {r.text}")
        # make sure the `sha` and `size` received from ostreehub matches with the original one
        if r.json()["size"] != len(s["canonical-json"]):
            raise Exception("invalid content size is received from ostreehub; "
                            f"expected: {len(s['canonical-json'])}, received: {r.json()['size']}")
        if r.json()["sha256"] != s["sha256"]:
            raise Exception("invalid content hash is received from ostreehub; "
                            f"expected: {s['sha256']}, received: {r.json()['sha256']}")


def _get_delta_stats(repo: str, from_sha: str, to_sha: str) -> dict:
    stat_out = cmd("ostree", "static-delta",
                   "show", f"--repo={repo}", f"{from_sha}-{to_sha}", capture=True)
    stat_out_lines = stat_out.splitlines()
    # parse output of the `ostree static-delta show` command
    stats = {}
    indx = 0
    for s in [("Total Uncompressed Size:", "u_size"), ("Total Size:", "size")]:
        stat_line = stat_out_lines[len(stat_out_lines) - 1 - indx].decode()
        if not stat_line.startswith(s[0]):
            raise Exception("Invalid static delta statistic output;"
                            f" expected {s[0]}, got {stat_line}")
        end_pos = stat_line[len(s[0]):].find("(")
        if -1 == end_pos:
            raise Exception("Invalid static delta statistic output;"
                            f" expected to find `(<value>)`, got {stat_line}")
        stats[s[1]] = int(stat_line[len(s[0]):len(s[0]) + end_pos].strip())
        indx += 1
    return stats
