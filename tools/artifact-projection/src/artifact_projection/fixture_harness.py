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


def _snapshot_tree(root: Path) -> Dict[str, bytes]:
    snap: Dict[str, bytes] = {}
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_dir():
            snap[rel + "/"] = b""
        else:
            snap[rel] = p.read_bytes()
    return snap


def _copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def _compare_trees(expected_root: Path, actual_root: Path) -> Tuple[bool, str]:
    exp = _snapshot_tree(expected_root)
    act = _snapshot_tree(actual_root)
    if exp == act:
        return True, ""
    exp_keys = set(exp.keys())
    act_keys = set(act.keys())
    missing = sorted(exp_keys - act_keys)[:10]
    extra = sorted(act_keys - exp_keys)[:10]
    changed = []
    for k in sorted(exp_keys & act_keys):
        if exp[k] != act[k]:
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
        config_path = d / "repo" / "config.json"
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
        expected_outcome = expect.get("expected_outcome")
        if expected_outcome not in OUTCOMES:
            failures.append(f"{fx.fixture_id}: invalid expected_outcome")
            continue

        with tempfile.TemporaryDirectory(prefix=f"ap_fixture_{fx.fixture_id}_") as td:
            td_path = Path(td)
            repo_copy = td_path / "repo"
            _copy_tree(fx.repo_dir, repo_copy)

            before = _snapshot_tree(repo_copy)
            outcome, rc, out = _run_projection(repo_copy, env)
            after = _snapshot_tree(repo_copy)

            if outcome != expected_outcome:
                failures.append(f"{fx.fixture_id}: outcome mismatch expected={expected_outcome} actual={outcome} rc={rc}")
                continue

            if expected_outcome == "EXPORTED_CLEAN":
                if not fx.expected_repo_dir.is_dir():
                    failures.append(f"{fx.fixture_id}: expected_repo/ missing for success fixture")
                    continue
                ok, msg = _compare_trees(fx.expected_repo_dir, repo_copy)
                if not ok:
                    failures.append(f"{fx.fixture_id}: tree mismatch: {msg}")
                    continue
            else:
                if before != after:
                    failures.append(f"{fx.fixture_id}: failure changed repo-visible state")
                    continue

    if failures:
        print("FAILED_REPRESENTATION: fixture mismatch")
        for f in failures:
            print(f"- {f}")
        return 3

    print("EXPORTED_CLEAN")
    return 0
