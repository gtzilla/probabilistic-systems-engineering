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


def refine_body_html(body_html: str) -> str:
    def normalize_li_classes(match: re.Match[str]) -> str:
        attrs = match.group("attrs") or ""
        class_match = re.search(r'class\s*=\s*"([^"]*)"', attrs, flags=re.IGNORECASE)
        if not class_match:
            return match.group(0)

        classes = [c for c in class_match.group(1).split() if not re.fullmatch(r"c\d+", c)]
        if classes:
            new_attrs = re.sub(
                r'class\s*=\s*"([^"]*)"',
                'class="' + " ".join(classes) + '"',
                attrs,
                count=1,
                flags=re.IGNORECASE,
            )
        else:
            new_attrs = re.sub(r'\s*class\s*=\s*"([^"]*)"', '', attrs, count=1, flags=re.IGNORECASE)

        return f"<li{new_attrs}>"

    body_html = re.sub(
        r"<li\b(?P<attrs>[^>]*)>",
        normalize_li_classes,
        body_html,
        flags=re.IGNORECASE,
    )

    def strip_tags(raw: str) -> str:
        text = re.sub(r"<[^>]+>", " ", raw)
        return html.unescape(re.sub(r"\s+", " ", text)).strip()

    def has_structural_content(raw: str) -> bool:
        return bool(re.search(r"<(img|svg|table|hr)\b", raw, flags=re.IGNORECASE))

    def is_empty_paragraph(inner_html: str) -> bool:
        if has_structural_content(inner_html):
            return False
        text = strip_tags(inner_html)
        return not text


    def normalize_p_attrs(attrs: str) -> str:
        class_match = re.search(r'class\s*=\s*"([^"]*)"', attrs, flags=re.IGNORECASE)
        if not class_match:
            return attrs

        classes = [
            c for c in class_match.group(1).split()
            if not re.fullmatch(r"c\d+", c)
        ]
        if classes:
            return re.sub(
                r'class\s*=\s*"([^"]*)"',
                'class="' + " ".join(classes) + '"',
                attrs,
                count=1,
                flags=re.IGNORECASE,
            )
        return re.sub(r'\s*class\s*=\s*"([^"]*)"', '', attrs, count=1, flags=re.IGNORECASE)

    paragraph_pattern = re.compile(r"<p\b(?P<attrs>[^>]*)>(?P<body>.*?)</p>", flags=re.IGNORECASE | re.DOTALL)
    pieces: list[dict[str, str | bool]] = []
    last_end = 0

    for match in paragraph_pattern.finditer(body_html):
        if match.start() > last_end:
            pieces.append({"kind": "raw", "html": body_html[last_end:match.start()]})

        attrs = normalize_p_attrs(match.group("attrs") or "")
        inner = match.group("body") or ""
        full = match.group(0)
        text = strip_tags(inner)
        classes_match = re.search(r'class\s*=\s*"([^"]*)"', attrs, flags=re.IGNORECASE)
        class_list = (classes_match.group(1).split() if classes_match else [])

        pieces.append(
            {
                "kind": "p",
                "html": full,
                "attrs": attrs,
                "inner": inner,
                "text": text,
                "is_empty": is_empty_paragraph(inner),
                "has_structural": has_structural_content(inner),
                "class_list": class_list,
            }
        )
        last_end = match.end()

    if last_end < len(body_html):
        pieces.append({"kind": "raw", "html": body_html[last_end:]})

    visible_paragraph_indexes = [
        idx
        for idx, piece in enumerate(pieces)
        if piece.get("kind") == "p" and not piece.get("is_empty")
    ]

    def add_class(attrs: str, class_name: str) -> str:
        class_match = re.search(r'class\s*=\s*"([^"]*)"', attrs, flags=re.IGNORECASE)
        if class_match:
            classes = class_match.group(1).split()
            if class_name not in classes:
                classes.append(class_name)
            return re.sub(
                r'class\s*=\s*"([^"]*)"',
                'class="' + " ".join(classes) + '"',
                attrs,
                count=1,
                flags=re.IGNORECASE,
            )
        return f'{attrs} class="{class_name}"'

    callout_indexes: set[int] = set()
    lead_in_indexes: set[int] = set()
    compact_indexes: set[int] = set()

    for pos, idx in enumerate(visible_paragraph_indexes):
        piece = pieces[idx]
        text = str(piece.get("text", ""))
        class_list = set(piece.get("class_list", []))
        if piece.get("has_structural"):
            continue
        if {"title", "subtitle", "pse-callout"} & class_list:
            continue

        if text.endswith(":") and len(text) <= 140 and pos + 1 < len(visible_paragraph_indexes):
            lead_in_indexes.add(idx)
            continue

        if 110 <= len(text) <= 420 and pos > 0:
            prev_piece = pieces[visible_paragraph_indexes[pos - 1]]
            prev_text = str(prev_piece.get("text", ""))
            if prev_text.endswith(":"):
                if pos + 1 < len(visible_paragraph_indexes):
                    next_piece = pieces[visible_paragraph_indexes[pos + 1]]
                    next_text = str(next_piece.get("text", ""))
                    if not next_text.endswith(":"):
                        callout_indexes.add(idx)
                        continue
                else:
                    callout_indexes.add(idx)
                    continue

        if len(text) <= 95:
            compact_indexes.add(idx)

    out: list[str] = []
    for idx, piece in enumerate(pieces):
        if piece.get("kind") != "p":
            out.append(str(piece.get("html", "")))
            continue

        if piece.get("is_empty"):
            continue

        attrs = str(piece.get("attrs", ""))
        inner = str(piece.get("inner", ""))

        if idx in callout_indexes:
            attrs = add_class(attrs, "pse-callout")
            out.append(f"<p{attrs}>{inner}</p>")
            continue

        if idx in lead_in_indexes:
            attrs = add_class(attrs, "pse-lead-in")
            out.append(f"<p{attrs}>{inner}</p>")
            continue

        if idx in compact_indexes:
            attrs = add_class(attrs, "pse-compact")
            out.append(f"<p{attrs}>{inner}</p>")
            continue

        out.append(f"<p{attrs}>{inner}</p>")

    return "".join(out)


def render_document_page(raw_html: str, pdf_href: str, doc_title: str) -> str:
    normalized = normalize_exported_html(raw_html)
    exported_styles = extract_head_styles(normalized)
    body_html = refine_body_html(extract_body_inner_html(normalized))

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



def discover_doc_dirs(type_root: Path) -> list[tuple[Path, str]]:
    docs: list[tuple[Path, str]] = []

    for dirpath, dirnames, filenames in os.walk(type_root):
        current = Path(dirpath)
        dirnames[:] = sorted(d for d in dirnames if not d.startswith("."))
        files = [name for name in filenames if not name.startswith(".")]
        pdfs = [name for name in files if name.lower().endswith(".pdf")]
        zips = [name for name in files if name.lower().endswith(".zip")]

        if pdfs or zips:
            if len(pdfs) != 1:
                fail(f"{current}: expected exactly one PDF matching *.pdf, found {len(pdfs)}")
            if len(zips) != 1:
                fail(f"{current}: expected exactly one ZIP matching *.zip, found {len(zips)}")
            docs.append((current, current.relative_to(type_root).as_posix()))
            dirnames[:] = []

    return sorted(docs, key=lambda item: item[1])


def build_doc(type_name: str, doc_dir: Path, relative_slug: str, tmp_root: Path) -> dict[str, str]:
    slug = relative_slug
    pdf = find_exactly_one(doc_dir, "*.pdf", "PDF")
    zf = find_exactly_one(doc_dir, "*.zip", "ZIP")

    extract_dir = tmp_root / type_name / Path(relative_slug)
    extract_dir.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(zf) as z:
        z.extractall(extract_dir)

    html_files = sorted(p for p in extract_dir.rglob("*.html") if p.is_file())
    if len(html_files) != 1:
        fail(f"{doc_dir}: expected exactly one HTML file after extraction, found {len(html_files)}")

    source_html = html_files[0]
    out_dir = DIST / type_name / Path(relative_slug)
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


def humanize_slug(slug: str) -> str:
    parts = [part for part in slug.split("-") if part]
    out: list[str] = []
    for part in parts:
        if re.fullmatch(r"v\d+(?:\.\d+)*", part, flags=re.IGNORECASE):
            out.append(part)
        else:
            out.append(part.capitalize())
    return " ".join(out) if out else slug


def split_group_and_leaf(slug: str) -> tuple[str, str]:
    parts = [p for p in slug.split("/") if p]
    if len(parts) <= 1:
        return ("", slug)
    return (humanize_slug(parts[0]), parts[-1])


def render_item_card(item: dict[str, str]) -> str:
    is_pdf_only = item.get("pdf_only") == "true"
    primary_href = item.get("url") if (not is_pdf_only and item.get("url")) else item.get("pdf_url", "")

    actions: list[str] = []
    if not is_pdf_only and item.get("url"):
        actions.append(f'<a class="item-action" href="{safe_text(item["url"])}">Read</a>')
    actions.append(f'<a class="item-action" href="{safe_text(item["pdf_url"])}">PDF</a>')
    meta = " · ".join(actions)

    if primary_href:
        title_html = (
            f'<a class="item-title-link" href="{safe_text(primary_href)}">'
            f'{safe_text(item["title"])}'
            '</a>'
        )
    else:
        title_html = safe_text(item["title"])

    return (
        '<li class="archive-item">'
        f'<div class="item-title">{title_html}</div>'
        f'<div class="item-actions">{meta}</div>'
        '</li>'
    )


def render_sections(items: list[dict[str, str]], empty_label: str) -> str:
    if not items:
        return f'<div class="empty-state">{safe_text(empty_label)}</div>'

    grouped: dict[str, list[dict[str, str]]] = {}
    for item in sorted(items, key=lambda x: x["title"].lower()):
        group_name, _leaf = split_group_and_leaf(item["slug"])
        grouped.setdefault(group_name, []).append(item)

    blocks: list[str] = []
    for group_name, group_items in grouped.items():
        rendered_items = "\n".join(render_item_card(item) for item in group_items)
        heading_html = f'<h3>{safe_text(group_name)}</h3>' if group_name else ''
        blocks.append(
            '<section class="group-block">'
            f'{heading_html}'
            '<ul class="archive-list">'
            f'{rendered_items}'
            '</ul>'
            '</section>'
        )
    return "\n".join(blocks)


def render_index(entries: list[dict[str, str]]) -> str:
    grouped: dict[str, list[dict[str, str]]] = {k: [] for k in CONTENT_TYPES}
    for entry in entries:
        grouped[entry["type"]].append(entry)

    template = load_template("index.html")
    return render_template(
        template,
        {
            "SITE_NAME": safe_text(SITE_NAME),
            "AUTHOR_NAME": safe_text("Gregory Tomlinson"),
            "HERO_TEXT": safe_text(
                "Research archive on probabilistic systems, contract-centered engineering, iterative stability, and authority in AI-assisted development."
            ),
            "PAPERS_SECTIONS": render_sections(grouped["papers"], "No papers yet."),
            "CONTRACTS_SECTIONS": render_sections(grouped["contracts"], "No contracts yet."),
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

            for doc_dir, relative_slug in discover_doc_dirs(type_root):
                entries.append(build_doc(type_name, doc_dir, relative_slug, tmp_root))

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
