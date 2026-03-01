import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from .config import load_config
from .discovery import find_eligible_pdfs, EligiblePdf
from .mapping import compute_paths, DeterministicPaths
from .meta import Meta, write_meta_file, read_meta_file
from .classify import scan_invalid_meta_is_fatal, classify_current_state
from .collisions import DtsPaths, evaluate_collisions
from .convert.pdf2htmlex_pandoc import convert_pdf_to_markdown, DEGRADED_MARKER
from .errors import FailedPolicy, FailedOperational, FailedRepresentation
from .staging import with_staging_workspace, copy_markdown_tree
from .util import sha256_file, compute_changed_paths, is_under_markdown


@dataclass(frozen=True)
class DesiredUnit:
    eligible: EligiblePdf
    paths: DeterministicPaths
    pdf_sha256: str


def _self_trigger_guard(repo_root: Path) -> bool:
    # §17: If all ChangedPaths are under markdown/: exit without convergence.
    changed = compute_changed_paths(repo_root)
    if changed is None:
        return False
    if len(changed) == 0:
        return False
    return all(is_under_markdown(p) for p in changed)


def run_convergence(repo_root: Path, config_path: Path) -> str:
    if _self_trigger_guard(repo_root):
        return "SKIPPED_SELF_TRIGGER"

    cfg = load_config(config_path)

    # §8.1 invalid meta is fatal (before any convergence attempt)
    scan_invalid_meta_is_fatal(repo_root)

    # DesiredSet (§10.1): eligible PDFs
    try:
        eligible = find_eligible_pdfs(repo_root, cfg)
    except ValueError as e:
        raise FailedPolicy(str(e))

    desired_units: List[DesiredUnit] = []
    desired_by_identity: Dict[Tuple[str, str], Tuple[str, str, str]] = {}  # (source_path, root_id) -> (det_md, det_meta, output_rel)
    dts_md: List[str] = []
    dts_meta: List[str] = []

    for e in eligible:
        paths = compute_paths(e)
        pdf_sha = sha256_file(repo_root / e.source_path)
        du = DesiredUnit(eligible=e, paths=paths, pdf_sha256=pdf_sha)
        desired_units.append(du)
        desired_by_identity[(e.source_path, e.root_id)] = (paths.md_path, paths.meta_path, paths.output_rel_path)
        dts_md.append(paths.md_path)
        dts_meta.append(paths.meta_path)

    dts_all = dts_md + dts_meta
    det_md_set = set(dts_md)
    det_meta_set = set(dts_meta)

    # Classify current markdown state (§9), producing LRS + unmanaged
    classification = classify_current_state(
        repo_root=repo_root,
        desired_by_identity=desired_by_identity,
        det_meta_paths=det_meta_set,
        det_md_paths=det_md_set,
    )

    # Collisions (§11). LRS is excluded by classification.unmanaged definition.
    evaluate_collisions(DtsPaths(all_paths=dts_all, md_paths=dts_md, meta_paths=dts_meta), classification.unmanaged)

    # LRS (§10.3): all Managed Residue paths
    lrs = set(classification.managed_residue)

    # §12 Strict Deletion Model
    allow_del = os.environ.get("ARTIFACT_PROJECTION_ALLOW_DELETIONS") == "true"
    if not allow_del and len(lrs) > 0:
        raise FailedPolicy("LRS non-empty and deletions not allowed (ARTIFACT_PROJECTION_ALLOW_DELETIONS != 'true')")

    # §13 Regeneration Rules
    to_regen: List[DesiredUnit] = []
    for du in desired_units:
        det_meta_path = repo_root / du.paths.meta_path
        det_md_path = repo_root / du.paths.md_path
        if det_meta_path.exists() and det_md_path.exists():
            meta = read_meta_file(det_meta_path)
            if (
                meta.pdf_sha256 == du.pdf_sha256 and
                meta.root_id == du.eligible.root_id and
                meta.source_path == du.eligible.source_path and
                meta.engine_id == cfg.engine_id
            ):
                continue
        to_regen.append(du)

    with_staging_workspace(lambda ws: _stage_validate_apply(
        repo_root=repo_root,
        engine_id=cfg.engine_id,
        desired_by_identity=desired_by_identity,
        det_md_set=det_md_set,
        det_meta_set=det_meta_set,
        dts_all=set(dts_all),
        to_regen=to_regen,
        lrs=lrs,
        unmanaged=classification.unmanaged,
        allow_del=allow_del,
        ws_path=ws.path,
    ))

    return "EXPORTED_CLEAN"


def _stage_validate_apply(
    repo_root: Path,
    engine_id: str,
    desired_by_identity: Dict[Tuple[str, str], Tuple[str, str, str]],
    det_md_set: Set[str],
    det_meta_set: Set[str],
    dts_all: Set[str],
    to_regen: List[DesiredUnit],
    lrs: Set[str],
    unmanaged: Set[str],
    allow_del: bool,
    ws_path: Path,
) -> None:
    # §15 stage mutations
    copy_markdown_tree(repo_root, type("WS", (), {"path": ws_path})())

    # Apply deletions (if allowed) inside staging
    if allow_del:
        for rel in sorted(lrs):
            p = ws_path / rel
            if p.exists() and p.is_file():
                p.unlink()

    # Regenerate required units into staging
    for du in to_regen:
        pdf_abs = repo_root / du.eligible.source_path
        md_res = convert_pdf_to_markdown(pdf_abs, engine_id=engine_id)
        md_out = ws_path / du.paths.md_path
        meta_out = ws_path / du.paths.meta_path
        md_out.parent.mkdir(parents=True, exist_ok=True)
        meta_out.parent.mkdir(parents=True, exist_ok=True)

        content = md_res.markdown
        if md_res.degraded_tables:
            content = DEGRADED_MARKER + "```text\n<degraded table extraction>\n```\n\n" + content
        md_out.write_text(content, encoding="utf-8")

        write_meta_file(meta_out, Meta(
            schema_version="2.2",
            source_path=du.eligible.source_path,
            root_id=du.eligible.root_id,
            pdf_sha256=du.pdf_sha256,
            engine_id=engine_id,
        ))

    # §16 Pre-Commit Validation (staged)
    _validate_staged(
        repo_root=repo_root,
        staged_root=ws_path,
        desired_by_identity=desired_by_identity,
        det_md_set=det_md_set,
        det_meta_set=det_meta_set,
        unmanaged=unmanaged,
    )

    # Apply staged markdown back to repo root (atomic repo-visible commit is via single git commit in workflow)
    staged_md = ws_path / "markdown"
    repo_md = repo_root / "markdown"

    if repo_md.exists():
        # Copy staged files over; do not touch unmanaged (already validated unchanged)
        for p in staged_md.rglob("*"):
            if p.is_dir():
                continue
            rel = p.relative_to(ws_path).as_posix()
            dest = repo_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dest)
        # If deletions allowed, ensure residue paths removed
        if allow_del:
            for rel in sorted(lrs):
                dest = repo_root / rel
                if dest.exists() and dest.is_file():
                    dest.unlink()
    else:
        shutil.copytree(staged_md, repo_md, dirs_exist_ok=True)


def _validate_staged(
    repo_root: Path,
    staged_root: Path,
    desired_by_identity: Dict[Tuple[str, str], Tuple[str, str, str]],
    det_md_set: Set[str],
    det_meta_set: Set[str],
    unmanaged: Set[str],
) -> None:
    # No invalid meta exists (schema) in staged tree
    mdroot = staged_root / "markdown"
    if mdroot.exists():
        for p in mdroot.rglob("*.meta.json"):
            _ = read_meta_file(p)

    # LRS empty: recompute classification in staged view and ensure no MR remains
    cls = classify_current_state(
        repo_root=staged_root,
        desired_by_identity=desired_by_identity,
        det_meta_paths=det_meta_set,
        det_md_paths=det_md_set,
    )
    if len(cls.managed_residue) != 0:
        raise FailedPolicy(f"Pre-commit validation failed: LRS not empty in staged tree: {sorted(cls.managed_residue)[:10]}")

    # All DTS units exist as MFUs: for each desired identity, deterministic md+meta exist and meta corresponds
    for ident, (mdp, metap, output_rel) in desired_by_identity.items():
        md_abs = staged_root / mdp
        meta_abs = staged_root / metap
        if not md_abs.exists() or not meta_abs.exists():
            raise FailedPolicy(f"Pre-commit validation failed: DTS unit missing for {ident} at {mdp} / {metap}")
        meta = read_meta_file(meta_abs)
        if (meta.source_path, meta.root_id) != ident:
            raise FailedPolicy(f"Pre-commit validation failed: meta identity mismatch at {metap}")

    # Unmanaged not modified/deleted
    for rel in unmanaged:
        src = repo_root / rel
        dst = staged_root / rel
        if not dst.exists():
            raise FailedPolicy(f"Pre-commit validation failed: Unmanaged deleted in staging: {rel}")
        if src.read_bytes() != dst.read_bytes():
            raise FailedPolicy(f"Pre-commit validation failed: Unmanaged modified in staging: {rel}")
