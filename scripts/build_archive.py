#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import html
import json
import os
import re
import shutil
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming"
DIST = ROOT / "dist"
TEMPLATES = ROOT / "scripts" / "templates"
SITE_NAME = "Probabilistic Systems Engineering"
CONTENT_TYPES = ["papers", "contracts"]


def fail(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    raise SystemExit(1)


def safe_text(s: str) -> str:
    return html.escape(s, quote=True)


def find_exactly_one(folder: Path, pattern: str, label: str) -> Path:
    matches = sorted(p for p in folder.glob(pattern) if p.is_file())
    if len(matches) != 1:
        fail(f"{folder}: expected exactly one {label} matching {pattern}, found {len(matches)}")
    return matches[0]


def load_template(name: str) -> str:
    path = TEMPLATES / name
    if not path.exists():
        fail(f"Missing template: {path}")
    return path.read_text(encoding="utf-8")


def render_template(template: str, values: dict[str, str]) -> str:
    out = template
    for key, value in values.items():
        out = out.replace(f"{{{{{key}}}}}", value)
    return out


def normalize_exported_html(raw_html: str) -> str:
    """
    Clean obvious Google Docs export junk in the top preamble only.

    Rules:
    - remove empty <p class="... title ...">...</p> blocks
    - remove duplicate non-empty title paragraphs in the preamble
    - stop touching content once the first structural section marker appears
      (<hr>, <h1>, <h2>, <h3>)
    """

    split_match = re.search(
        r"(<hr\b[^>]*>|<h1\b[^>]*>|<h2\b[^>]*>|<h3\b[^>]*>)",
        raw_html,
        flags=re.IGNORECASE,
    )
    if not split_match:
        return raw_html

    preamble = raw_html[: split_match.start()]
    rest = raw_html[split_match.start() :]

    title_pat = re.compile(
        r'(<p\b[^>]*class="[^"]*\btitle\b[^"]*"[^>]*>.*?</p>)',
        flags=re.IGNORECASE | re.DOTALL,
    )
    tag_pat = re.compile(r"<[^>]+>")
    seen_titles: set[str] = set()

    def repl(match: re.Match[str]) -> str:
        block = match.group(1)
        text = tag_pat.sub("", block)
        text = html.unescape(text).strip()

        if not text:
            return ""

        if text in seen_titles:
            return ""

        seen_titles.add(text)
        return block

    cleaned_preamble = title_pat.sub(repl, preamble)
    return cleaned_preamble + rest


def inject_head_metadata(raw_html: str, doc_title: str) -> str:
    page_title = f"{doc_title} | {SITE_NAME}"
    description = f"{doc_title} — published in {SITE_NAME}."

    raw_html = re.sub(
        r"<title\b[^>]*>.*?</title>",
        f"<title>{safe_text(page_title)}</title>",
        raw_html,
        flags=re.IGNORECASE | re.DOTALL,
        count=1,
    )

    lower = raw_html.lower()
    head_close = lower.find("</head>")
    if head_close != -1:
        before_close = raw_html[:head_close]
        additions = []
        if "<meta name=\"description\"" not in before_close.lower():
            additions.append(f'  <meta name="description" content="{safe_text(description)}">')
        if "<meta name=\"author\"" not in before_close.lower():
            additions.append('  <meta name="author" content="Gregory Tomlinson">')
        if additions:
            raw_html = raw_html[:head_close] + "\n" + "\n".join(additions) + "\n" + raw_html[head_close:]
        return raw_html

    return (
        "<head>\n"
        f"  <title>{safe_text(page_title)}</title>\n"
        f'  <meta name="description" content="{safe_text(description)}">\n'
        '  <meta name="author" content="Gregory Tomlinson">\n'
        "</head>\n"
        + raw_html
    )


def extract_head_styles(raw_html: str) -> str:
    """
    Return all <style>...</style> blocks from the exported HTML head/body.
    Google Docs puts critical document styling here.
    """
    matches = re.findall(r"(<style\b[^>]*>.*?</style>)", raw_html, flags=re.IGNORECASE | re.DOTALL)
    return "\n".join(matches)


def extract_body_inner_html(raw_html: str) -> str:
    match = re.search(r"<body\b[^>]*>(.*)</body>", raw_html, flags=re.IGNORECASE | re.DOTALL)
    if match:
        return match.group(1).strip()
    return raw_html.strip()


def render_document_page(raw_html: str, pdf_href: str, doc_title: str) -> str:
    normalized = normalize_exported_html(raw_html)
    exported_styles = extract_head_styles(normalized)
    body_html = extract_body_inner_html(normalized)

    template = load_template("document_shell.html")
    return render_template(
        template,
        {
            "PAGE_TITLE": safe_text(f"{doc_title} | {SITE_NAME}"),
            "PAGE_DESCRIPTION": safe_text(f"{doc_title} — published in {SITE_NAME}."),
            "SITE_NAME": safe_text(SITE_NAME),
            "HOME_HREF": "../../",
            "PDF_HREF": safe_text(pdf_href),
            "EXPORTED_STYLES": exported_styles,
            "DOCUMENT_BODY": body_html,
        },
    )




def compute_dist_hash(dist_root: Path) -> str:
    hasher = hashlib.sha256()
    for path in sorted(p for p in dist_root.rglob("*") if p.is_file() and p.name != "build.json"):
        rel = path.relative_to(dist_root).as_posix().encode("utf-8")
        digest = hashlib.sha256(path.read_bytes()).hexdigest().encode("utf-8")
        hasher.update(rel)
        hasher.update(b"\0")
        hasher.update(digest)
        hasher.update(b"\0")
    return hasher.hexdigest()


def write_build_manifest(dist_root: Path) -> None:
    manifest = {
        "site": SITE_NAME,
        "source_sha": os.getenv("GITHUB_SHA", ""),
        "source_ref": os.getenv("GITHUB_REF_NAME", ""),
        "built_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "dist_hash": compute_dist_hash(dist_root),
    }
    (dist_root / "build.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")



def copy_pdf_to_durable_artifact(type_name: str, slug: str, pdf: Path) -> None:
    durable_dir = ROOT / type_name / slug
    durable_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(pdf, durable_dir / pdf.name)

def build_doc(type_name: str, slug_dir: Path, tmp_root: Path) -> dict[str, str]:
    slug = slug_dir.name
    pdf = find_exactly_one(slug_dir, "*.pdf", "PDF")
    zf = find_exactly_one(slug_dir, "*.zip", "ZIP")

    extract_dir = tmp_root / type_name / slug
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zf) as z:
        z.extractall(extract_dir)

    html_files = sorted(p for p in extract_dir.rglob("*.html") if p.is_file())
    if len(html_files) != 1:
        fail(f"{slug_dir}: expected exactly one HTML file after extraction, found {len(html_files)}")

    source_html = html_files[0]
    out_dir = DIST / type_name / slug
    out_dir.mkdir(parents=True, exist_ok=True)

    # Copy extracted assets/files except the source HTML itself.
    for child in extract_dir.iterdir():
        if child.resolve() == source_html.resolve():
            continue
        dest = out_dir / child.name
        if child.is_dir():
            shutil.copytree(child, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(child, dest)

    pdf_href = pdf.name
    doc_title = pdf.stem
    raw_html = source_html.read_text(encoding="utf-8")
    wrapped_html = render_document_page(raw_html, pdf_href, doc_title)
    (out_dir / "index.html").write_text(wrapped_html, encoding="utf-8")
    shutil.copy2(pdf, out_dir / pdf.name)
    copy_pdf_to_durable_artifact(type_name, slug, pdf)

    return {
        "type": type_name,
        "slug": slug,
        "pdf_name": pdf.name,
        "title": pdf.stem,
        "url": f"./{type_name}/{slug}/",
        "pdf_url": f"./{type_name}/{slug}/{pdf.name}",
    }


def collect_pdf_only_contract_entries(entries: list[dict[str, str]]) -> list[dict[str, str]]:
    existing_contract_slugs = {
        entry["slug"]
        for entry in entries
        if entry["type"] == "contracts"
    }

    contracts_root = ROOT / "contracts"
    if not contracts_root.exists() or not contracts_root.is_dir():
        return entries

    for slug_dir in sorted(p for p in contracts_root.iterdir() if p.is_dir()):
        slug = slug_dir.name
        if slug in existing_contract_slugs:
            continue

        pdfs = sorted(p for p in slug_dir.glob("*.pdf") if p.is_file())
        if len(pdfs) == 0:
            continue
        if len(pdfs) > 1:
            fail(f"{slug_dir}: expected at most one PDF for PDF-only contract listing, found {len(pdfs)}")

        pdf = pdfs[0]

        out_dir = DIST / "contracts" / slug
        out_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(pdf, out_dir / pdf.name)

        entries.append(
            {
                "type": "contracts",
                "slug": slug,
                "pdf_name": pdf.name,
                "title": pdf.stem,
                "url": "",
                "pdf_url": f"./contracts/{slug}/{pdf.name}",
                "pdf_only": "true",
            }
        )

    return entries


def render_group(label: str, items: list[dict[str, str]]) -> str:
    lis = []
    for item in sorted(items, key=lambda x: x["title"].lower()):
        is_pdf_only = item.get("pdf_only") == "true"
        if is_pdf_only:
            lis.append(
                f'<li>{safe_text(item["title"])} — <a href="{safe_text(item["pdf_url"])}">PDF</a></li>'
            )
        else:
            lis.append(
                f'<li><a href="{safe_text(item["url"])}">{safe_text(item["title"])}</a>'
                f' — <a href="{safe_text(item["pdf_url"])}">PDF</a></li>'
            )
    return "\n".join(lis) if lis else "<li>None yet.</li>"


def render_index(entries: list[dict[str, str]]) -> str:
    grouped: dict[str, list[dict[str, str]]] = {k: [] for k in CONTENT_TYPES}
    for entry in entries:
        grouped[entry["type"]].append(entry)

    template = load_template("index.html")
    return render_template(
        template,
        {
            "SITE_NAME": safe_text(SITE_NAME),
            "PAPERS_LIST": render_group("Papers", grouped["papers"]),
            "CONTRACTS_LIST": render_group("Contracts", grouped["contracts"]),
        },
    )


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
            if not type_root.is_dir():
                fail(f"{type_root} exists but is not a directory")

            for slug_dir in sorted(p for p in type_root.iterdir() if p.is_dir()):
                entries.append(build_doc(type_name, slug_dir, tmp_root))

        entries = collect_pdf_only_contract_entries(entries)

        (DIST / "index.html").write_text(render_index(entries), encoding="utf-8")
        write_build_manifest(DIST)
        print(f"Built archive into {DIST}")
        return 0
    finally:
        if tmp_root.exists():
            shutil.rmtree(tmp_root)


if __name__ == "__main__":
    raise SystemExit(main())