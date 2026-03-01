from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Tuple

OUTCOMES = {"EXPORTED_CLEAN", "FAILED_OPERATIONAL", "FAILED_REPRESENTATION", "FAILED_POLICY"}

FIXTURES_ROOT = Path("tools/artifact-projection/fixtures")


@dataclass(frozen=True)
class Fixture:
    fixture_id: str
    path: Path
    repo_dir: Path
    config_path: Path
    expect_path: Path
    expected_repo_dir: Path


def _load_json(path: Path) -> Dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_bytes(path: Path) -> bytes:
    return path.read_bytes()


def _snapshot_paths(root: Path, rel_paths: List[str]) -> Dict[str, bytes]:
    snap: Dict[str, bytes] = {}
    for rel in rel_paths:
        p = root / rel
        if rel.endswith("/"):
            # directory marker
            if not p.is_dir():
                snap[rel] = b"__MISSING_DIR__"
            else:
                snap[rel] = b""
            continue
        if p.is_dir():
            # represent directory as marker
            snap[rel + "/"] = b""
        elif p.is_file():
            snap[rel] = _read_bytes(p)
        else:
            snap[rel] = b"__MISSING__"
    return snap



def _snapshot_expected_files(expected_repo_dir: Path, repo_root: Path) -> Tuple[Dict[str, bytes], Dict[str, bytes]]:
    # Compare only files present in expected_repo/markdown to allow unmanaged files to exist.
    exp_files: Dict[str, bytes] = {}
    act_files: Dict[str, bytes] = {}
    md_root = expected_repo_dir / "markdown"
    if not md_root.exists():
        return exp_files, act_files
    for p in sorted(md_root.rglob("*")):
        if p.is_dir():
            continue
        rel = p.relative_to(expected_repo_dir).as_posix()  # markdown/...
        exp_files[rel] = p.read_bytes()
        act_p = repo_root / rel
        if act_p.is_file():
            act_files[rel] = act_p.read_bytes()
        else:
            act_files[rel] = b"__MISSING__"
    return exp_files, act_files


def _snapshot_tree_under(root: Path, subdir: str) -> Dict[str, bytes]:
    base = root / subdir
    snap: Dict[str, bytes] = {}
    if not base.exists():
        return snap
    for p in sorted(base.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_dir():
            snap[rel + "/"] = b""
        else:
            snap[rel] = p.read_bytes()
    return snap


def _compare_snap(expected: Dict[str, bytes], actual: Dict[str, bytes]) -> Tuple[bool, str]:
    if expected == actual:
        return True, ""
    exp_keys = set(expected.keys())
    act_keys = set(actual.keys())
    missing = sorted(exp_keys - act_keys)[:10]
    extra = sorted(act_keys - exp_keys)[:10]
    changed = []
    for k in sorted(exp_keys & act_keys):
        if expected[k] != actual[k]:
            changed.append(k)
            if len(changed) >= 10:
                break
    return False, f"missing={missing} extra={extra} changed={changed}"


def discover_fixtures() -> List[Fixture]:
    if not FIXTURES_ROOT.exists():
        raise RuntimeError("fixtures root missing")
    out: List[Fixture] = []
    for d in sorted([p for p in FIXTURES_ROOT.iterdir() if p.is_dir()]):
        repo_dir = d / "repo"
        config_path = repo_dir / "config.json"
        expect_path = d / "expect.json"
        expected_repo_dir = d / "expected_repo"
        if not repo_dir.is_dir():
            raise RuntimeError(f"{d.name}: missing repo/")
        if not config_path.is_file():
            raise RuntimeError(f"{d.name}: missing repo/config.json")
        if not expect_path.is_file():
            raise RuntimeError(f"{d.name}: missing expect.json")
        out.append(Fixture(d.name, d, repo_dir, config_path, expect_path, expected_repo_dir))
    return out


def _run_projection(repo_root: Path, env: Dict[str, str]) -> Tuple[str, int, str]:
    proc = subprocess.run(
        ["python", "-m", "artifact_projection", "--config", "config.json"],
        cwd=str(repo_root),
        text=True,
        capture_output=True,
        env=env,
    )
    combined = (proc.stdout or "") + (proc.stderr or "")
    for o in OUTCOMES:
        if o in combined:
            return o, proc.returncode, combined
    # fallback
    if proc.returncode == 0:
        return "EXPORTED_CLEAN", 0, combined
    if proc.returncode == 1:
        return "FAILED_POLICY", 1, combined
    if proc.returncode == 2:
        return "FAILED_OPERATIONAL", 2, combined
    if proc.returncode == 3:
        return "FAILED_REPRESENTATION", 3, combined
    return "FAILED_OPERATIONAL", proc.returncode, combined


def run_fixtures(*, allow_deletions: bool) -> int:
    failures: List[str] = []
    env = os.environ.copy()
    env["ARTIFACT_PROJECTION_ALLOW_DELETIONS"] = "true" if allow_deletions else "false"

    for fx in discover_fixtures():
        expect = _load_json(fx.expect_path)
        # Per-fixture allow_deletions override (fixture suite contains both cases).
        per_allow = expect.get("allow_deletions")
        if per_allow is None:
            env["ARTIFACT_PROJECTION_ALLOW_DELETIONS"] = "true" if allow_deletions else "false"
        else:
            env["ARTIFACT_PROJECTION_ALLOW_DELETIONS"] = "true" if bool(per_allow) else "false"
        expected_outcome = expect.get("expected_outcome")
        expect_changed = expect.get("expect_changed_paths", [])
        expect_unchanged = expect.get("expect_unchanged_paths", [])
        if expected_outcome not in OUTCOMES:
            failures.append(f"{fx.fixture_id}: invalid expected_outcome")
            continue
        if not isinstance(expect_changed, list) or not isinstance(expect_unchanged, list):
            failures.append(f"{fx.fixture_id}: invalid expect_changed_paths/expect_unchanged_paths")
            continue

        with tempfile.TemporaryDirectory(prefix=f"ap_fixture_{fx.fixture_id}_") as td:
            td_path = Path(td)
            repo_copy = td_path / "repo"
            shutil.copytree(fx.repo_dir, repo_copy)

            before_changed = _snapshot_paths(repo_copy, expect_changed)
            before_unchanged = _snapshot_paths(repo_copy, expect_unchanged)

            outcome, rc, out = _run_projection(repo_copy, env)

            after_changed = _snapshot_paths(repo_copy, expect_changed)
            after_unchanged = _snapshot_paths(repo_copy, expect_unchanged)

            if outcome != expected_outcome:
                failures.append(f"{fx.fixture_id}: outcome mismatch expected={expected_outcome} actual={outcome} rc={rc}")
                continue

            # unchanged assertions always apply
            ok, msg = _compare_snap(before_unchanged, after_unchanged)
            if not ok:
                failures.append(f"{fx.fixture_id}: unchanged_paths violated: {msg}")
                continue

            if expected_outcome == "EXPORTED_CLEAN":
                # changed paths should differ or exist newly (best-effort check)
                # For paths that are created, before snapshot will be __MISSING__
                # We don't require byte-different (some outputs may be identical), but we require existence not missing.
                for rel in expect_changed:
                    if rel.endswith("/"):
                        if not (repo_copy / rel).is_dir():
                            failures.append(f"{fx.fixture_id}: expected created dir missing: {rel}")
                            break
                    else:
                        if not (repo_copy / rel).exists():
                            failures.append(f"{fx.fixture_id}: expected changed path missing: {rel}")
                            break
                else:
                    # compare managed scope only: markdown/ subtree must match expected_repo/markdown subtree
                    exp_md, act_md = _snapshot_expected_files(fx.expected_repo_dir, repo_copy)
                    ok2, msg2 = _compare_snap(exp_md, act_md)
                    if not ok2:
                        failures.append(f"{fx.fixture_id}: managed markdown tree mismatch: {msg2}")
                        continue
            else:
                # failure must leave no visible change at all (stronger than needed but matches v2.3 patch intent)
                # Compare whole tree by walking all files/dirs under repo_copy and original
                # (cheap: compare git-style snapshots)
                def snap_all(root: Path) -> Dict[str, bytes]:
                    snap: Dict[str, bytes] = {}
                    for p in sorted(root.rglob("*")):
                        rel = p.relative_to(root).as_posix()
                        if p.is_dir():
                            snap[rel + "/"] = b""
                        else:
                            snap[rel] = p.read_bytes()
                    return snap
                if snap_all(repo_copy) != snap_all(fx.repo_dir):
                    failures.append(f"{fx.fixture_id}: failure changed repo-visible state")
                    continue

    if failures:
        print("FAILED_REPRESENTATION: fixture mismatch")
        for f in failures:
            print(f"- {f}")
        return 3

    print("EXPORTED_CLEAN")
    return 0
