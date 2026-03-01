from __future__ import annotations

import re
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
            ["pandoc", "--from", "markdown", "--to", "gfm", "--wrap=none"],
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


_ZW_CHARS_RE = re.compile("[\u200b\u200c\u200d\ufeff\u00ad\u2060]")
_BULLET_LINE_RE = re.compile(r"(?m)^\s*[•\u2022\u25cf\u25e6\u25aa\u25a0]\s*")
_BULLET_INLINE_AFTER_COLON_RE = re.compile(r"(:)\s*[•\u2022\u25cf\u25e6\u25aa\u25a0]\s*")
_COLON_TIGHT_LIST_RE = re.compile(r"(?m):(\n- )")

_HEADING_LINE_RE = re.compile(r"^(?P<num>\d+(?:\.\d+)*)(?:\.)\s+(?P<rest>.+?)\s*$")
_HEADING_SPLIT_SENTINEL_RE = re.compile(
    r"\s+(The|A|An|In|For|Used|Each|This|These|Externally|Violation|Required|Stability)\b"
)


def _normalize_extracted_text(page_text: str) -> str:
    """Normalize PyMuPDF text extraction into pandoc-friendly markdown.

    PyMuPDF returns plain text with some PDF artifacts:
    - zero-width chars / soft hyphens
    - bullet glyphs (●) rather than markdown list markers
    - headings sometimes glued to their body on a single line

    This function is intentionally heuristic and only targets readability +
    pandoc block parsing rules (blank lines before lists/headings).
    """

    t = page_text.replace("\r\n", "\n").replace("\r", "\n")
    t = _ZW_CHARS_RE.sub("", t)

    # Bullet glyphs -> markdown list markers.
    # If list begins immediately after a colon, insert a blank line for pandoc.
    t = _BULLET_INLINE_AFTER_COLON_RE.sub(r"\1\n\n- ", t)
    t = _BULLET_LINE_RE.sub("- ", t)
    t = _COLON_TIGHT_LIST_RE.sub(":\n\n- ", t)

    out_lines: list[str] = []
    for raw in t.split("\n"):
        line = raw.strip()

        if not line:
            out_lines.append("")
            continue

        # Turn numbered headings into markdown headings.
        # Example: "2.1 Authority Domain The Authority Domain is ...".
        m = _HEADING_LINE_RE.match(line)
        if m:
            num = m.group("num")
            rest = m.group("rest").strip()

            # Split inline heading "<title> <body>" using sentinel words.
            title = rest
            body: str | None = None
            sm = _HEADING_SPLIT_SENTINEL_RE.search(rest)
            if sm and sm.start() > 0:
                title = rest[: sm.start()].rstrip()
                body = rest[sm.start() + 1 :].lstrip()  # skip leading space

            dots = num.count(".")
            level = 3 + min(dots, 2)  # ### .. #####
            if out_lines and out_lines[-1].strip():
                out_lines.append("")
            out_lines.append("#" * level + f" {num}. {title}")
            out_lines.append("")
            if body:
                out_lines.append(body)
            continue

        out_lines.append(raw.rstrip())

    norm = "\n".join(out_lines)
    norm = re.sub(r"\n{3,}", "\n\n", norm)
    return norm.strip()


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
        text = _normalize_extracted_text(text)
        parts.append(f"## Page {i}\n")
        parts.append(text + "\n")
    raw_md = "\n".join(parts).strip() + "\n"
    norm_md = _run_pandoc_normalize_gfm(raw_md)
    return ConvertResult(markdown=norm_md, degraded_tables=False)
