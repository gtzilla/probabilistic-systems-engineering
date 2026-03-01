from __future__ import annotations

import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

from ..errors import FailedOperational


DEGRADED_MARKER = "<!-- ARTIFACT_PROJECTION_DEGRADED -->\n"


@dataclass(frozen=True)
class ConvertResult:
    markdown: str
    degraded_tables: bool


def _fixture_markdown(pdf_path: Path) -> str:
    return f"# {pdf_path.name}\n\nFixture projection.\n"


def convert_pdf_to_markdown(pdf_path: Path, *, engine_id: str) -> ConvertResult:
    if engine_id.startswith("fixture-degraded"):
        return ConvertResult(markdown=_fixture_markdown(pdf_path), degraded_tables=True)

    if engine_id.startswith("fixture-stable"):
        return ConvertResult(markdown=_fixture_markdown(pdf_path), degraded_tables=False)

    # Real engine routing.
    # - If engine_id indicates PyMuPDF, bypass pdf2htmlEX entirely.
    if "pymupdf" in engine_id.lower():
        from .pandoc_pymupdf import convert_pdf_to_markdown as convert_pdf_to_markdown_pymupdf
        return convert_pdf_to_markdown_pymupdf(pdf_path)

    with tempfile.TemporaryDirectory(prefix="artifact_projection_pdf_") as td:
        html_path = Path(td) / "out.html"

        try:
            proc = subprocess.run(
                ["pdf2htmlEX", str(pdf_path), str(html_path)],
                cwd="/",
                text=True,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError as e:
            raise FailedOperational("required tool not found on PATH: pdf2htmlEX") from e

        if proc.returncode != 0:
            raise FailedOperational(f"pdf2htmlEX failed rc={proc.returncode}: {proc.stderr.strip()}")

        try:
            proc2 = subprocess.run(
                ["pandoc", "--from", "html", "--to", "gfm", "--wrap=none", str(html_path)],
                text=True,
                capture_output=True,
                check=False,
            )
        except FileNotFoundError as e:
            raise FailedOperational("required tool not found on PATH: pandoc") from e

        if proc2.returncode != 0:
            raise FailedOperational(f"pandoc failed rc={proc2.returncode}: {proc2.stderr.strip()}")

        md = proc2.stdout
        if not md.endswith("\n"):
            md += "\n"
        return ConvertResult(markdown=md, degraded_tables=False)
