import hashlib
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

ASCII_UPPER = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def ascii_case_fold(s: str) -> str:
    # ASCII folding applies ONLY to letters A–Z and a–z.
    out = []
    for ch in s:
        if "A" <= ch <= "Z":
            out.append(chr(ord(ch) + 32))
        else:
            out.append(ch)
    return "".join(out)

def is_under_markdown(p: str) -> bool:
    return p == "markdown" or p.startswith("markdown/")

def run_git(repo_root: Path, args: List[str]) -> Tuple[int, str, str]:
    proc = subprocess.Popen(
        ["git", *args],
        cwd=str(repo_root),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    out, err = proc.communicate()
    return proc.returncode, out, err

def compute_changed_paths(repo_root: Path) -> Optional[List[str]]:
    # Best-effort. If cannot compute, return None meaning "unknown" (proceed).
    # Attempt HEAD^..HEAD
    rc, out, err = run_git(repo_root, ["rev-parse", "--verify", "HEAD^"])
    if rc != 0:
        return None
    rc, out, err = run_git(repo_root, ["diff", "--name-only", "HEAD^..HEAD"])
    if rc != 0:
        return None
    paths = [line.strip() for line in out.splitlines() if line.strip()]
    return paths

def normalize_repo_rel_path(p: str) -> str:
    # Repository-relative paths; byte-for-byte comparisons; no OS normalization implied.
    # We still forbid backslashes and absolute paths at config boundaries.
    if p.startswith("/"):
        raise ValueError("path must be repo-relative, not absolute")
    if "\\" in p:
        raise ValueError("path must use '/' separators")
    # keep as-is otherwise
    return p

def validate_root_path(root_path: str) -> None:
    # §4.3 constraints
    if root_path == "":
        raise ValueError("root_path must be non-empty")
    if root_path.startswith("/") or root_path.endswith("/"):
        raise ValueError("root_path must not start/end with '/'")
    if "//" in root_path:
        raise ValueError('root_path must not contain "//"')
    segs = root_path.split("/")
    if any(seg in (".", "..") for seg in segs):
        raise ValueError('root_path must not contain "." or ".." segments')
    if root_path == "markdown":
        raise ValueError('root_path must not equal "markdown"')
    # Not a segment-prefix of markdown and vice versa
    if is_segment_prefix(root_path, "markdown") or is_segment_prefix("markdown", root_path):
        raise ValueError('root_path must not overlap markdown by segment-prefix')

def is_segment_prefix(a: str, b: str) -> bool:
    # §4.2
    return b == a or b.startswith(a + "/")
