import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

@dataclass(frozen=True)
class StagingWorkspace:
    path: Path

def with_staging_workspace(fn: Callable[[StagingWorkspace], None]) -> None:
    with tempfile.TemporaryDirectory(prefix="artifact_projection_") as td:
        ws = StagingWorkspace(path=Path(td))
        fn(ws)

def copy_markdown_tree(repo_root: Path, ws: StagingWorkspace) -> Path:
    src = repo_root / "markdown"
    dst = ws.path / "markdown"
    if src.exists():
        shutil.copytree(src, dst, dirs_exist_ok=True)
    else:
        dst.mkdir(parents=True, exist_ok=True)
    return dst
