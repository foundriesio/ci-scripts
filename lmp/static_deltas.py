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
    for delta in deltas:
        for f in delta.froms:
            sha, _ = f
            status("Generating delta", with_ts=True)
            cmd("ostree", "static-delta",
                          "generate", f"--repo={repo}", "--from", sha, "--to", delta.to[0])
            prog.tick()
