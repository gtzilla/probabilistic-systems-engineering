import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from .errors import FailedPolicy

_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")

REQUIRED_KEYS = ("schema_version", "source_path", "root_id", "pdf_sha256", "engine_id")

@dataclass(frozen=True)
class Meta:
    schema_version: str
    source_path: str
    root_id: str
    pdf_sha256: str
    engine_id: str

def parse_meta_json(text: str) -> Meta:
    try:
        obj = json.loads(text)
    except Exception as e:
        raise FailedPolicy(f"Invalid meta.json (not JSON): {e}")
    if not isinstance(obj, dict):
        raise FailedPolicy("Invalid meta.json: not an object")
    keys = tuple(obj.keys())
    if set(keys) != set(REQUIRED_KEYS) or len(keys) != len(REQUIRED_KEYS):
        raise FailedPolicy("Invalid meta.json: keys must be exactly schema_version, source_path, root_id, pdf_sha256, engine_id")
    if obj.get("schema_version") != "2.2":
        raise FailedPolicy('Invalid meta.json: schema_version must be "2.2"')
    for k in REQUIRED_KEYS:
        if not isinstance(obj.get(k), str):
            raise FailedPolicy(f"Invalid meta.json: {k} must be a string")
    sha = obj["pdf_sha256"]
    if not _SHA256_RE.match(sha):
        raise FailedPolicy("Invalid meta.json: pdf_sha256 must be lowercase hex sha256")
    return Meta(
        schema_version=obj["schema_version"],
        source_path=obj["source_path"],
        root_id=obj["root_id"],
        pdf_sha256=obj["pdf_sha256"],
        engine_id=obj["engine_id"],
    )

def read_meta_file(path: Path) -> Meta:
    return parse_meta_json(path.read_text(encoding="utf-8"))

def write_meta_file(path: Path, meta: Meta) -> None:
    obj = {
        "schema_version": "2.2",
        "source_path": meta.source_path,
        "root_id": meta.root_id,
        "pdf_sha256": meta.pdf_sha256,
        "engine_id": meta.engine_id,
    }
    path.write_text(json.dumps(obj, indent=2, sort_keys=False) + "\n", encoding="utf-8")
