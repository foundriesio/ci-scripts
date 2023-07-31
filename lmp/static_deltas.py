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
        for from_sha, _ in delta.froms:
            cmd("ostree", "static-delta",
                "generate", f"--repo={repo}", "--from", from_sha, "--to", delta.to[0])
            prog.tick()
