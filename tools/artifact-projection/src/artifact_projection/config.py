import json
from dataclasses import dataclass
from pathlib import Path
from typing import List

from .util import normalize_repo_rel_path, validate_root_path, is_segment_prefix

@dataclass(frozen=True)
class SourceRoot:
    root_id: str
    root_path: str
    recursive: bool

@dataclass(frozen=True)
class Config:
    engine_id: str
    roots: List[SourceRoot]

def load_config(path: Path) -> Config:
    raw = json.loads(path.read_text())
    if not isinstance(raw, dict):
        raise ValueError("config must be a JSON object")
    engine_id = raw.get("engine_id")
    roots_raw = raw.get("roots")
    if not isinstance(engine_id, str) or engine_id.strip() == "":
        raise ValueError("engine_id must be a non-empty string")
    if not isinstance(roots_raw, list) or len(roots_raw) == 0:
        raise ValueError("roots must be a non-empty list")
    roots: List[SourceRoot] = []
    for r in roots_raw:
        if not isinstance(r, dict):
            raise ValueError("each root must be an object")
        root_id = r.get("root_id")
        root_path = r.get("root_path")
        recursive = r.get("recursive")
        if not isinstance(root_id, str) or root_id.strip() == "":
            raise ValueError("root_id must be a non-empty string")
        if not isinstance(root_path, str) or root_path.strip() == "":
            raise ValueError("root_path must be a non-empty string")
        if not isinstance(recursive, bool):
            raise ValueError("recursive must be boolean")
        root_path = normalize_repo_rel_path(root_path)
        validate_root_path(root_path)
        roots.append(SourceRoot(root_id=root_id, root_path=root_path, recursive=recursive))

    # Uniqueness of root_id and root_path
    ids = [r.root_id for r in roots]
    if len(set(ids)) != len(ids):
        raise ValueError("root_id values must be unique")
    paths = [r.root_path for r in roots]
    if len(set(paths)) != len(paths):
        raise ValueError("root_path values must be unique")

    # Root non-overlap by segment-prefix
    for i in range(len(roots)):
        for j in range(i + 1, len(roots)):
            a = roots[i].root_path
            b = roots[j].root_path
            if is_segment_prefix(a, b) or is_segment_prefix(b, a):
                raise ValueError(f"root_path overlap by segment-prefix: {a!r} vs {b!r}")

    return Config(engine_id=engine_id, roots=roots)
