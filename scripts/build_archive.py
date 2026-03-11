#!/usr/bin/env python3
from __future__ import annotations

import html
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming"
DIST = ROOT / "dist"
SITE_NAME = "Probabilistic Systems Engineering"
CONTENT_TYPES = ["papers", "contracts"]


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def find_exactly_one(folder: Path, pattern: str, label: str) -> Path:
    matches = sorted(folder.glob(pattern))
    if len(matches) != 1:
        fail(f"{folder}: expected exactly one {label} matching {pattern}, found {len(matches)}")
    return matches[0]


def safe_text(s: str) -> str:
    return html.escape(s, quote=True)


def wrap_document_html(raw_html: str, pdf_url: str) -> str:
    style = """
<style>
  .pse-topbar {
    border-bottom: 1px solid #e5e5e5;
    margin-bottom: 2rem;
  }
  .pse-topbar-inner {
    max-width: 1100px;
    margin: 0 auto;
    padding: 0.9rem 1rem;
    display: flex;
    gap: 1rem;
    align-items: center;
    justify-content: space-between;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
  .pse-site-link {
    color: #111;
    text-decoration: none;
    font-weight: 600;
  }
  .pse-site-link:hover,
  .pse-nav a:hover {
    text-decoration: underline;
  }
  .pse-nav {
    display: flex;
    gap: 1rem;
    align-items: center;
  }
  .pse-nav a {
    color: #444;
    text-decoration: none;
  }
  .pse-footer {
    margin: 3rem auto 1.5rem;
    max-width: 1100px;
    padding: 0 1rem;
    color: #666;
    font-size: 0.95rem;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
  }
</style>
"""

    topbar = f"""
<header class="pse-topbar">
  <div class="pse-topbar-inner">
    <a class="pse-site-link" href="/">{safe_text(SITE_NAME)}</a>
    <nav class="pse-nav">
      <a href="/">Home</a>
      <a href="{safe_text(pdf_url)}">PDF</a>
    </nav>
  </div>
</header>
"""

    footer = """
<footer class="pse-footer">Authored by Gregory Tomlinson</footer>
"""

    lower = raw_html.lower()

    head_close = lower.find("</head>")
    if head_close != -1:
        raw_html = raw_html[:head_close] + style + raw_html[head_close:]
    else:
        raw_html = style + raw_html

    body_open = raw_html.lower().find("<body")
    if body_open != -1:
        body_tag_end = raw_html.find(">", body_open)
        if body_tag_end != -1:
            raw_html = raw_html[: body_tag_end + 1] + topbar + raw_html[body_tag_end + 1 :]
    else:
        raw_html = topbar + raw_html

    body_close = raw_html.lower().rfind("</body>")
    if body_close != -1:
        raw_html = raw_html[:body_close] + footer + raw_html[body_close:]
    else:
        raw_html = raw_html + footer

    return raw_html


def build_doc(type_name: str, slug_dir: Path, tmp_root: Path) -> dict[str, str]:
    slug = slug_dir.name
    pdf = find_exactly_one(slug_dir, "*.pdf", "PDF")
    zf = find_exactly_one(slug_dir, "*.zip", "ZIP")

    extract_dir = tmp_root / type_name / slug
    extract_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zf) as z:
        z.extractall(extract_dir)

    html_files = sorted(extract_dir.rglob("*.html"))
    if len(html_files) != 1:
        fail(f"{slug_dir}: expected exactly one HTML file after extraction, found {len(html_files)}")
    source_html = html_files[0]

    out_dir = DIST / type_name / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    # copy all extracted files/folders as-is into output, preserving relative structure
    for child in extract_dir.iterdir():
        dest = out_dir / child.name
        if child.is_dir():
            shutil.copytree(child, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(child, dest)

    pdf_url = f"/{type_name}/{slug}/{pdf.name}"
    wrapped_html = wrap_document_html(source_html.read_text(encoding="utf-8"), pdf_url)
    (out_dir / "index.html").write_text(wrapped_html, encoding="utf-8")
    shutil.copy2(pdf, out_dir / pdf.name)

    return {
        "type": type_name,
        "slug": slug,
        "pdf_name": pdf.name,
        "title": pdf.name,
        "url": f"/{type_name}/{slug}/",
        "pdf_url": pdf_url,
    }


def render_index(entries: list[dict[str, str]]) -> str:
    grouped: dict[str, list[dict[str, str]]] = {k: [] for k in CONTENT_TYPES}
    for entry in entries:
        grouped[entry["type"]].append(entry)

    def render_group(label: str, items: list[dict[str, str]]) -> str:
        lis = []
        for item in sorted(items, key=lambda x: x["title"].lower()):
            lis.append(
                f'<li><a href="{safe_text(item["url"])}">{safe_text(item["title"])}</a>'
                f' — <a href="{safe_text(item["pdf_url"])}">PDF</a></li>'
            )
        inner = "\n".join(lis) if lis else "<li>None yet.</li>"
        return f"<section><h2>{label}</h2><ul>{inner}</ul></section>"

    body = "\n".join([
        render_group("Papers", grouped["papers"]),
        render_group("Contracts", grouped["contracts"]),
    ])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_text(SITE_NAME)}</title>
  <style>
    body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; margin: 2rem auto; max-width: 900px; padding: 0 1rem; line-height: 1.5; }}
    h1 {{ margin-bottom: 1.5rem; }}
    section {{ margin: 2rem 0; }}
    ul {{ padding-left: 1.25rem; }}
    li {{ margin: .4rem 0; }}
  </style>
</head>
<body>
  <h1>{safe_text(SITE_NAME)}</h1>
  {body}
</body>
</html>
"""


def main() -> int:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)

    tmp_root = ROOT / ".build_tmp"
    if tmp_root.exists():
        shutil.rmtree(tmp_root)
    tmp_root.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, str]] = []
    try:
        for type_name in CONTENT_TYPES:
            type_root = INCOMING / type_name
            if not type_root.exists():
                continue
            for slug_dir in sorted(p for p in type_root.iterdir() if p.is_dir()):
                entries.append(build_doc(type_name, slug_dir, tmp_root))

        (DIST / "index.html").write_text(render_index(entries), encoding="utf-8")
        print(f"Built archive into {DIST}")
        return 0
    finally:
        if tmp_root.exists():
            shutil.rmtree(tmp_root)


if __name__ == "__main__":
    raise SystemExit(main())