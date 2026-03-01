from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from .config import Config, SourceRoot
from .util import is_segment_prefix

@dataclass(frozen=True)
class EligiblePdf:
    source_path: str   # repo-relative path
    root_id: str
    root_path: str
    recursive: bool

def _iter_files_under(repo_root: Path, root_path: str, recursive: bool) -> List[str]:
    base = repo_root / root_path
    if not base.exists() or not base.is_dir():
        return []
    out: List[str] = []
    if recursive:
        for p in base.rglob("*"):
            if p.is_file():
                rel = p.relative_to(repo_root).as_posix()
                out.append(rel)
    else:
        for p in base.iterdir():
            if p.is_file():
                rel = p.relative_to(repo_root).as_posix()
                out.append(rel)
    return out

def find_eligible_pdfs(repo_root: Path, cfg: Config) -> List[EligiblePdf]:
    # Build list of candidate files under each root, apply membership rule and .pdf suffix.
    candidates: Dict[str, List[Tuple[SourceRoot, str]]] = {}
    for root in cfg.roots:
        files = _iter_files_under(repo_root, root.root_path, root.recursive)
        for f in files:
            candidates.setdefault(f, []).append((root, f))

    eligible: List[EligiblePdf] = []
    for source_path, matches in candidates.items():
        # must end with .pdf (case-sensitive)
        if not source_path.endswith(".pdf"):
            continue

        # determine roots under which it "resides" per §5.1, using segment-prefix and source_path != root_path
        residing = []
        for root, f in matches:
            if is_segment_prefix(root.root_path, source_path) and source_path != root.root_path:
                residing.append(root)

        if len(residing) == 0:
            continue
        if len(residing) > 1:
            # multi-root match is FAILED_POLICY (handled by caller)
            # return marker with special root_id to convey failure surface
            raise ValueError(f"source_path matches more than one root: {source_path} -> {[r.root_id for r in residing]}")

        root = residing[0]
        if not root.recursive:
            # §5.2 parent_dir(source_path) must equal root_path byte-for-byte
            parent = source_path.rsplit("/", 1)[0] if "/" in source_path else ""
            if parent != root.root_path:
                continue

        eligible.append(EligiblePdf(source_path=source_path, root_id=root.root_id, root_path=root.root_path, recursive=root.recursive))

    return sorted(eligible, key=lambda e: (e.root_id, e.source_path))
