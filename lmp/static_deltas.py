import hashlib
import canonicaljson
from typing import List, NamedTuple, Tuple

from helpers import (
    Progress,
    status,
    cmd
)


class Delta(NamedTuple):
    to: Tuple[str, str]
    froms: List[Tuple[str, str]]


def generate_deltas(prog: Progress, deltas: List[Delta], repo: str):
    delta_stats = {}
    for delta in deltas:
        to_sha, _ = delta.to
        delta_stat = {to_sha: {}}
        for f in delta.froms:
            from_sha, _ = f
            status("Generating delta", with_ts=True)
            cmd("ostree", "static-delta",
                          "generate", f"--repo={repo}", "--from", from_sha, "--to", to_sha)
            stat_out = cmd("ostree", "static-delta",
                           "show", f"--repo={repo}", f"{from_sha}-{to_sha}", capture=True)
            delta_stat[to_sha][from_sha] = {}
            stat_out_lines = stat_out.splitlines()
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
                delta_stat[to_sha][from_sha][s[1]] = int(stat_line[len(s[0]):len(s[0]) + end_pos].strip())
                indx += 1

            prog.tick()
        delta_stat_json = canonicaljson.encode_canonical_json(delta_stat)
        delta_stat_json_sha = hashlib.sha256()
        delta_stat_json_sha.update(delta_stat_json)
        delta_stats[to_sha] = {
            "sha256": delta_stat_json_sha.hexdigest(),
            "canonical-json": delta_stat_json
        }

    return delta_stats
