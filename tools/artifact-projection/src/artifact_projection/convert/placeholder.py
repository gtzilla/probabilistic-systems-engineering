from dataclasses import dataclass
from pathlib import Path
from typing import Optional

DEGRADED_MARKER = "<!-- ARTIFACT_PROJECTION_DEGRADED -->\n"

@dataclass(frozen=True)
class ConvertResult:
    markdown: str
    degraded_tables: bool

def convert_pdf_to_markdown_placeholder(pdf_path: Path) -> ConvertResult:
    # Deterministic placeholder conversion. Real engine can replace this.
    # Produces stable content based on path only.
    md = f"# PDF Projection\n\nSource: `{pdf_path.as_posix()}`\n"
    return ConvertResult(markdown=md, degraded_tables=False)
