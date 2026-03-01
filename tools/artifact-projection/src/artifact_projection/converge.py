from __future__ import annotations

import hashlib
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

from .convert.pdf2htmlex_pandoc import convert_pdf_to_markdown, DEGRADED_MARKER
from .meta import SCHEMA_VERSION
from .errors import FailedPolicy, FailedOperational, FailedRepresentation


@dataclass(frozen=True)
class Root:
    root_id: str
    root_path: str
    recursive: bool


def _load_config(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _eligible_pdfs(repo_root: Path, roots: List[Root]) -> List[Tuple[Root, Path, str]]:
    # returns list of (root, abs_path, source_rel_posix)
    matches: List[Tuple[Root, Path, str]] = []
    for r in roots:
        root_abs = (repo_root / r.root_path).resolve()
        if not root_abs.exists():
            continue
        if r.recursive:
            it = root_abs.rglob("*.pdf")
        else:
            it = root_abs.glob("*.pdf")
        for p in sorted(it):
            if not p.is_file():
                continue
            rel = p.relative_to(repo_root).as_posix()
            matches.append((r, p, rel))
    return matches


def _detect_multi_root_ambiguity(matches: List[Tuple[Root, Path, str]]) -> None:
    # A given source_rel must match exactly one root_id
    seen: Dict[str, str] = {}
    for r, p, rel in matches:
        if rel in seen and seen[rel] != r.root_id:
            raise FailedPolicy(f"Multi-root ambiguity for {rel}: {seen[rel]} vs {r.root_id}")
        seen[rel] = r.root_id


def _deterministic_output_base(*, root_path: str, source_rel: str) -> str:
    # Output base path relative to the configured root_path, without .pdf extension.
    # Example: root_path="pdf", source_rel="pdf/a.pdf" -> "a"
    # Example: root_path="papers", source_rel="papers/sub/x.pdf" -> "sub/x"
    if not source_rel.lower().endswith(".pdf"):
        raise FailedOperational("source_rel is not a pdf")
    rp = root_path.strip("/")
    sr = source_rel.strip("/")
    if rp == ".":
        within = sr
    else:
        prefix = rp + "/"
        if not sr.startswith(prefix):
            # This should not happen if eligibility was computed correctly.
            raise FailedOperational(f"source_rel {source_rel} is not under root_path {root_path}")
        within = sr[len(prefix):]
    base = within[:-4]  # drop .pdf
    return base


def _casefold_key(path: str) -> str:
    # ASCII case-fold: lower() on A-Z
    return path.lower()


def _compute_dts_paths(output_base: str) -> Tuple[str, str]:
    md = f"markdown/{output_base}.md"
    meta = f"markdown/{output_base}.meta.json"
    return md, meta


def _assert_no_dts_collision(dts_pairs: List[Tuple[str, str, str]]) -> None:
    # dts_pairs: list of (source_rel, md_rel, meta_rel)
    seen: Dict[str, str] = {}
    for source_rel, md_rel, meta_rel in dts_pairs:
        k = _casefold_key(md_rel)
        if k in seen and seen[k] != source_rel:
            raise FailedPolicy(f"DTS collision (casefold) for {md_rel}: {seen[k]} vs {source_rel}")
        seen[k] = source_rel
        k2 = _casefold_key(meta_rel)
        if k2 in seen and seen[k2] != source_rel:
            raise FailedPolicy(f"DTS collision (casefold) for {meta_rel}: {seen[k2]} vs {source_rel}")
        seen[k2] = source_rel



def _assert_no_dts_vs_unmanaged_casefold(*, repo_root: Path, dts_targets: List[str], lrs_paths: List[str]) -> None:
    md_root = (repo_root / "markdown").resolve()
    if not md_root.exists():
        return
    lrs_set = set(lrs_paths)
    unmanaged_keys: Dict[str, str] = {}
    for p in md_root.rglob("*"):
        if p.is_dir():
            continue
        rel = p.relative_to(repo_root).as_posix()
        if rel in lrs_set:
            continue
        unmanaged_keys[_casefold_key(rel)] = rel
    for target in dts_targets:
        if target in lrs_set:
            continue
        k = _casefold_key(target)
        existing = unmanaged_keys.get(k)
        if existing is None:
            continue
        if existing != target:
            raise FailedPolicy(f"DTS vs Unmanaged collision (casefold) for {target}: existing {existing}")
def _assert_dts_not_unmanaged(repo_root: Path, md_rel: str, meta_rel: str, *, lrs_paths: List[str]) -> None:
    md_p = repo_root / md_rel
    meta_p = repo_root / meta_rel

    # LRS paths are logically removable and SHALL NOT trigger DTS vs Unmanaged policy failures.
    lrs_set = set(lrs_paths)
    if md_rel in lrs_set or meta_rel in lrs_set:
        return
    # Unmanaged collision includes non-file at target path
    if md_p.exists() and not md_p.is_file():
        raise FailedPolicy(f"DTS collides with unmanaged non-file path: {md_rel}")
    if meta_p.exists() and not meta_p.is_file():
        raise FailedPolicy(f"DTS collides with unmanaged non-file path: {meta_rel}")


def _detect_lrs(repo_root: Path, dts_pairs: List[Tuple[str, str, str]]) -> List[str]:
    # Managed residue: for a deterministic pair, exactly one of markdown/<base>.md and markdown/<base>.meta.json exists
    # AND the existing path is a regular file (directories are unmanaged and handled by DTS-vs-unmanaged policy).
    residues: List[str] = []
    for _, md_rel, meta_rel in dts_pairs:
        md_p = repo_root / md_rel
        meta_p = repo_root / meta_rel
        md_exists = md_p.exists()
        meta_exists = meta_p.exists()
        if md_exists and not meta_exists and md_p.is_file():
            residues.append(md_rel)
        elif meta_exists and not md_exists and meta_p.is_file():
            residues.append(meta_rel)
    return residues
def _delete_lrs(repo_root: Path, residues: List[str]) -> None:
    for rel in residues:
        p = (repo_root / rel).resolve()
        if not p.exists():
            continue
        if p.is_dir():
            shutil.rmtree(p)
        else:
            p.unlink()
def _write_file_atomic(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


def _write_text_atomic(path: Path, text: str) -> None:
    _write_file_atomic(path, text.encode("utf-8"))


def run_convergence(*, repo_root: Path, config_path: Path) -> str:
    cfg = _load_config(config_path)
    engine_id = cfg.get("engine_id")
    roots_cfg = cfg.get("roots", [])
    if not engine_id or not isinstance(roots_cfg, list) or not roots_cfg:
        raise FailedPolicy("config must include engine_id and non-empty roots[]")

    roots: List[Root] = []
    for r in roots_cfg:
        roots.append(Root(root_id=r["root_id"], root_path=r["root_path"], recursive=bool(r["recursive"])))

    matches = _eligible_pdfs(repo_root, roots)
    _detect_multi_root_ambiguity(matches)

    # Build deterministic mapping list
    dts_pairs: List[Tuple[str, str, str]] = []
    for r, abs_p, source_rel in matches:
        output_base = _deterministic_output_base(root_path=r.root_path, source_rel=source_rel)
        md_rel, meta_rel = _compute_dts_paths(output_base)
        dts_pairs.append((source_rel, md_rel, meta_rel))

    _assert_no_dts_collision(dts_pairs)

    # Managed residue handling
    allow_deletions = os.environ.get("ARTIFACT_PROJECTION_ALLOW_DELETIONS") == "true"
    residues = _detect_lrs(repo_root, dts_pairs)
    if residues and not allow_deletions:
        raise FailedPolicy("Managed residue exists and deletions are not allowed")
    if residues and allow_deletions:
        _delete_lrs(repo_root, residues)

    # DTS vs unmanaged checks (LRS is ignored for collision purposes)
    _assert_no_dts_vs_unmanaged_casefold(
        repo_root=repo_root,
        dts_targets=[md for _, md, _ in dts_pairs] + [meta for _, _, meta in dts_pairs],
        lrs_paths=residues,
    )
    for source_rel, md_rel, meta_rel in dts_pairs:
        _assert_dts_not_unmanaged(repo_root, md_rel, meta_rel, lrs_paths=residues)

    # Stage outputs in-memory then write (atomic per-file; repo-level atomicity relies on not touching on failure)
    staged: List[Tuple[str, bytes]] = []
    staged_meta: List[Tuple[str, bytes]] = []

    for r, abs_p, source_rel in matches:
        output_base = _deterministic_output_base(root_path=r.root_path, source_rel=source_rel)
        md_rel, meta_rel = _compute_dts_paths(output_base)

        pdf_bytes = abs_p.read_bytes()
        pdf_sha = _sha256_bytes(pdf_bytes)

        # convert
        md_res = convert_pdf_to_markdown(abs_p, engine_id=engine_id)
        md_text = md_res.markdown
        if md_res.degraded_tables:
            md_text = DEGRADED_MARKER + "```text\n<degraded table extraction>\n```\n\n" + md_text

        meta_obj = {
            "schema_version": SCHEMA_VERSION,
            "source_path": source_rel,
            "root_id": r.root_id,
            "pdf_sha256": pdf_sha,
            "engine_id": engine_id,
        }

        staged.append((md_rel, md_text.encode("utf-8")))
        staged_meta.append((meta_rel, (json.dumps(meta_obj, indent=2) + "\n").encode("utf-8")))

    # Write staged outputs
    for rel, data in staged:
        _write_file_atomic(repo_root / rel, data)
    for rel, data in staged_meta:
        _write_file_atomic(repo_root / rel, data)

    return "EXPORTED_CLEAN"
