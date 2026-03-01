from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Set, Tuple

from .meta import Meta, read_meta_file
from .errors import FailedPolicy
from .util import is_under_markdown

@dataclass(frozen=True)
class MfUnit:
    md_path: str
    meta_path: str
    meta: Meta

@dataclass(frozen=True)
class Classification:
    mfus: Dict[str, MfUnit]        # key: output_rel_path
    managed_residue: Set[str]      # paths under markdown/
    unmanaged: Set[str]            # paths under markdown/

def scan_invalid_meta_is_fatal(repo_root: Path) -> None:
    mdroot = repo_root / "markdown"
    if not mdroot.exists():
        return
    # If any .meta.json violates schema: FAILED_POLICY, no convergence attempt
    for p in mdroot.rglob("*.meta.json"):
        _ = read_meta_file(p)  # raises FailedPolicy if invalid

def classify_current_state(
    repo_root: Path,
    desired_by_identity: Dict[Tuple[str, str], Tuple[str, str, str]],
    # identity -> (det_md_path, det_meta_path, output_rel_path)
    det_meta_paths: Set[str],
    det_md_paths: Set[str],
) -> Classification:
    mdroot = repo_root / "markdown"
    all_under: Set[str] = set()
    if mdroot.exists():
        for p in mdroot.rglob("*"):
            if p.is_file():
                all_under.add(p.relative_to(repo_root).as_posix())

    # Start empty
    mfus: Dict[str, MfUnit] = {}
    mr: Set[str] = set()

    # MR-1: partial pair at deterministic path
    for mdp in det_md_paths:
        mp = mdp.replace(".md", ".meta.json")
        have_md = mdp in all_under
        have_meta = mp in all_under
        if have_md != have_meta:
            # whichever exists is MR (path-level residue)
            if have_md:
                mr.add(mdp)
            if have_meta:
                mr.add(mp)

    # Parse all schema-valid meta files (invalid already checked outside)
    meta_paths = [p for p in all_under if p.endswith(".meta.json")]
    metas: Dict[str, Meta] = {}
    for mp in meta_paths:
        metas[mp] = read_meta_file(repo_root / mp)

    # MR-2 / MR-3 classification based on meta semantics
    for mp, meta in metas.items():
        ident = (meta.source_path, meta.root_id)
        desired = desired_by_identity.get(ident)
        if desired is None:
            # MR-3 (non-eligible/orphan meta)
            mr.add(mp)
            continue
        det_md_path, det_meta_path, output_rel = desired
        if mp != det_meta_path:
            # MR-2 (mis-mapped valid meta)
            mr.add(mp)
        # MR-3 (pair incomplete: deterministic md missing), regardless of path correctness
        if det_md_path not in all_under:
            mr.add(mp)

    # MFU: both exist, schema-valid, corresponds to eligible artifact, mapping matches
    for ident, (det_md_path, det_meta_path, output_rel) in desired_by_identity.items():
        if det_md_path in all_under and det_meta_path in all_under:
            meta = metas.get(det_meta_path)
            if meta is None:
                continue
            # mapping match and identity match already implied by desired_by_identity key; also ensure meta fields exactly align
            if (meta.source_path, meta.root_id) != ident:
                continue
            mfus[output_rel] = MfUnit(md_path=det_md_path, meta_path=det_meta_path, meta=meta)

    unmanaged: Set[str] = set()
    for p in all_under:
        if p in mr:
            continue
        # MFU members are the deterministic md+meta paths for mfus
        is_mfu_member = any(p == u.md_path or p == u.meta_path for u in mfus.values())
        if is_mfu_member:
            continue
        unmanaged.add(p)

    return Classification(mfus=mfus, managed_residue=mr, unmanaged=unmanaged)
