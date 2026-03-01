from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

DEGRADED_MARKER = "<!-- ARTIFACT_PROJECTION_DEGRADED -->\n"


@dataclass(frozen=True)
class ConvertResult:
    markdown: str
    degraded_tables: bool


def _run_pandoc_normalize_gfm(markdown: str) -> str:
    """
    Normalize markdown using pandoc to GitHub-flavored markdown (gfm).

    Note: pandoc cannot directly convert PDF -> Markdown; per pandoc FAQ, PDF input
    is not supported. Here pandoc is used only to normalize markdown produced by
    the PDF text extraction step.
    """
    try:
        proc = subprocess.run(
            ["pandoc", "--from", "markdown", "--to", "gfm"],
            input=markdown,
            text=True,
            capture_output=True,
            check=False,
        )
    except FileNotFoundError as e:
        raise RuntimeError("pandoc is not installed on PATH") from e

    if proc.returncode != 0:
        raise RuntimeError(f"pandoc failed: rc={proc.returncode}: {proc.stderr.strip()}")

    return proc.stdout


def convert_pdf_to_markdown(pdf_path: Path) -> ConvertResult:
    """
    Deterministic PDF text extraction via PyMuPDF, then pandoc normalization to gfm.

    This implementation does not attempt table reconstruction; tables may be degraded
    into plain text. The contract allows a degraded marker path when table extraction
    fails, but we do not attempt table detection here.
    """
    doc = fitz.open(pdf_path)
    parts = [f"# {pdf_path.name}\n"]
    for i, page in enumerate(doc, start=1):
        text = page.get_text("text").strip()
        if not text:
            continue
        parts.append(f"## Page {i}\n")
        parts.append(text + "\n")
    raw_md = "\n".join(parts).strip() + "\n"
    norm_md = _run_pandoc_normalize_gfm(raw_md)
    return ConvertResult(markdown=norm_md, degraded_tables=False)
