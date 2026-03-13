#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter

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
SITE_URL = "https://archive.gtzilla.com"
CONTENT_TYPES = ["papers", "contracts", "replication"]
TYPE_LABELS = {"papers": "Papers", "contracts": "Contracts", "replication": "Replication"}


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


def safe_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def strip_tags_to_text(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def extract_candidate_paragraph_texts(body_html: str) -> list[str]:
    paragraphs: list[str] = []
    for match in re.finditer(r"<p\b[^>]*>(.*?)</p>", body_html, flags=re.IGNORECASE | re.DOTALL):
        inner = match.group(1)
        if re.search(r"<(img|svg|table|hr)\b", inner, flags=re.IGNORECASE):
            continue
        text = strip_tags_to_text(inner)
        if not text:
            continue
        paragraphs.append(text)
    return paragraphs


def detect_version(text: str) -> str:
    match = re.search(r"\bv\d+(?:\.\d+)*\b", text, flags=re.IGNORECASE)
    return match.group(0) if match else ""


def parse_version_tuple(version: str) -> tuple[int, ...]:
    if not version:
        return tuple()
    normalized = version.lower()
    if normalized.startswith("v"):
        normalized = normalized[1:]
    parts = [part for part in normalized.split(".") if part]
    values: list[int] = []
    for part in parts:
        if not part.isdigit():
            return tuple()
        values.append(int(part))
    return tuple(values)


def slug_family_info(slug: str) -> tuple[str, str, tuple[int, ...]]:
    parts = [part for part in slug.split("/") if part]
    if not parts:
        return ("", "", tuple())

    leaf = parts[-1]
    match = re.match(r"^(?P<family>.+)-(?P<version>v\d+(?:\.\d+)*)$", leaf, flags=re.IGNORECASE)
    if not match:
        return ("", "", tuple())

    family_leaf = match.group("family")
    version = match.group("version")
    family_parts = parts[:-1] + [family_leaf]
    return ("/".join(family_parts), version, parse_version_tuple(version))


def estimate_reading_time_minutes(text: str) -> int:
    words = len(re.findall(r"\S+", text))
    if words <= 0:
        return 1
    return max(1, (words + 219) // 220)


def metadata_kind_for_type(type_name: str) -> tuple[str, str]:
    if type_name == "papers":
        return ("paper", "ScholarlyArticle")
    if type_name == "contracts":
        return ("contract", "TechArticle")
    if type_name == "replication":
        return ("replication-material", "TechArticle")
    return (type_name, "CreativeWork")


def derive_description(paragraphs: list[str], doc_title: str) -> str:
    abstract = ""
    for paragraph in paragraphs:
        if len(paragraph) >= 80:
            abstract = paragraph
            break
    if not abstract and paragraphs:
        abstract = paragraphs[0]
    if len(abstract) > 320:
        abstract = abstract[:317].rstrip() + "..."
    return abstract or f"{doc_title} — published in {SITE_NAME}."


STOPWORDS = {
    "the", "and", "for", "with", "from", "this", "that", "into", "your", "about", "through",
    "under", "what", "when", "where", "which", "while", "have", "been", "will", "their", "more",
    "than", "only", "also", "does", "did", "not", "are", "was", "were", "how", "why", "who",
    "onto", "over", "then", "them", "they", "using", "used", "between", "because",
    "paper", "papers", "contract", "contracts", "report", "system", "program", "materials",
    "material", "version", "artifact", "artifacts", "document", "documents", "study", "work",
}


def normalize_for_match(text: str) -> str:
    lowered = html.unescape(text).lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def significant_tokens(text: str) -> list[str]:
    tokens = []
    for token in normalize_for_match(text).split():
        if len(token) < 4:
            continue
        if token in STOPWORDS:
            continue
        if re.fullmatch(r"v\d+(?:\.\d+)*", token):
            continue
        tokens.append(token)
    return tokens


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if not value or value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def slug_reference_phrases(slug: str) -> list[str]:
    parts = [p for p in slug.split("/") if p]
    phrases: list[str] = []
    if not parts:
        return []
    phrases.append(normalize_for_match(parts[-1].replace("-", " ")))
    phrases.append(normalize_for_match(slug.replace("/", " ").replace("-", " ")))
    return unique_preserve_order([p for p in phrases if len(p) >= 12])


def document_match_context(metadata: dict[str, object], full_text: str) -> dict[str, object]:
    title = str(metadata["title"])
    description = str(metadata.get("description", ""))
    slug = str(metadata["slug"])
    version = str(metadata.get("version", ""))
    title_tokens = unique_preserve_order(significant_tokens(title))
    description_tokens = unique_preserve_order(significant_tokens(description))
    return {
        "norm_text": normalize_for_match(full_text),
        "title_phrase": normalize_for_match(title),
        "slug_phrases": slug_reference_phrases(slug),
        "title_tokens": title_tokens,
        "description_tokens": description_tokens,
        "version": version.lower(),
    }


def derive_document_metadata(
    type_name: str,
    slug: str,
    doc_title: str,
    pdf_name: str,
    body_html: str,
) -> tuple[dict[str, object], dict[str, object]]:
    paragraphs = extract_candidate_paragraph_texts(body_html)
    description = derive_description(paragraphs, doc_title)

    full_text = " ".join(paragraphs)
    kind, schema_type = metadata_kind_for_type(type_name)
    version = detect_version(doc_title)
    slug_parts = [part for part in slug.split("/") if part]
    group_key = slug_parts[0] if len(slug_parts) > 1 else ""
    family_key, slug_version, version_tuple = slug_family_info(slug)
    effective_version = slug_version or version
    html_path = f"/{type_name}/{slug}/"
    pdf_path = f"/{type_name}/{slug}/{pdf_name}"

    metadata: dict[str, object] = {
        "kind": kind,
        "schema_type": schema_type,
        "content_type": type_name,
        "slug": slug,
        "title": doc_title,
        "author": "Gregory Tomlinson",
        "html_path": html_path,
        "html_url": f"{SITE_URL}{html_path}",
        "pdf_path": pdf_path,
        "pdf_url": f"{SITE_URL}{pdf_path}",
        "group_key": group_key,
        "family_key": family_key,
        "version": effective_version,
        "version_tuple": list(version_tuple),
        "description": description,
        "word_count": len(re.findall(r"\S+", full_text)),
        "reading_time_minutes": estimate_reading_time_minutes(full_text),
    }
    return metadata, document_match_context(metadata, full_text)


def build_structured_data(metadata: dict[str, object]) -> str:
    payload = {
        "@context": "https://schema.org",
        "@type": metadata["schema_type"],
        "name": metadata["title"],
        "headline": metadata["title"],
        "author": {
            "@type": "Person",
            "name": metadata["author"],
        },
        "description": metadata["description"],
        "url": metadata["html_url"],
        "mainEntityOfPage": metadata["html_url"],
        "encoding": {
            "@type": "MediaObject",
            "contentUrl": metadata["pdf_url"],
            "encodingFormat": "application/pdf",
            "name": metadata["pdf_url"].rsplit("/", 1)[-1],
        },
        "isAccessibleForFree": True,
        "keywords": [metadata["content_type"], metadata["kind"]],
        "timeRequired": f"PT{metadata['reading_time_minutes']}M",
    }
    if metadata.get("version"):
        payload["version"] = metadata["version"]
    if metadata.get("group_key"):
        payload["isPartOf"] = {
            "@type": "CreativeWorkSeries",
            "name": str(metadata["group_key"]).replace("-", " ").title(),
        }
    return safe_json(payload)


def write_site_metadata_index(
    dist_root: Path,
    entries: list[dict[str, str]],
    metadata_index: list[dict[str, object]],
) -> None:
    payload = {
        "site": SITE_NAME,
        "site_url": SITE_URL,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "documents": metadata_index,
    }
    metadata_dir = dist_root / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    (metadata_dir / "documents.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def write_sitemap(dist_root: Path, entries: list[dict[str, str]]) -> None:
    urls = [f"{SITE_URL}/", f"{SITE_URL}/latest/", f"{SITE_URL}/archive/"]
    for entry in entries:
        if entry.get("url"):
            urls.append(f"{SITE_URL}/{entry['url'].lstrip('./')}")
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]
    for url in urls:
        xml.append("  <url>")
        xml.append(f"    <loc>{safe_text(url)}</loc>")
        xml.append("  </url>")
    xml.append("</urlset>")
    (dist_root / "sitemap.xml").write_text("\n".join(xml) + "\n", encoding="utf-8")


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
        if '<meta name="description"' not in before_close.lower():
            additions.append(f'  <meta name="description" content="{safe_text(description)}">')
        if '<meta name="author"' not in before_close.lower():
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
            new_attrs = re.sub(r'\s*class\s*=\s*"([^"]*)"', "", attrs, count=1, flags=re.IGNORECASE)

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
        return re.sub(r'\s*class\s*=\s*"([^"]*)"', "", attrs, count=1, flags=re.IGNORECASE)

    paragraph_pattern = re.compile(r"<p\b(?P<attrs>[^>]*)>(?P<body>.*?)</p>", flags=re.IGNORECASE | re.DOTALL)
    pieces: list[dict[str, str | bool | list[str]]] = []
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

    title_piece_indexes = [
        idx
        for idx, piece in enumerate(pieces)
        if piece.get("kind") == "p" and "title" in set(piece.get("class_list", []))
    ]

    canonical_title_text = ""
    non_empty_title_texts = [
        str(pieces[idx].get("text", "")).strip()
        for idx in title_piece_indexes
        if str(pieces[idx].get("text", "")).strip()
    ]
    if non_empty_title_texts:
        counts = Counter(non_empty_title_texts)
        canonical_title_text = sorted(
            counts.items(),
            key=lambda item: (-item[1], -len(item[0]), item[0].lower()),
        )[0][0]

    title_indexes_to_keep: set[int] = set()
    if canonical_title_text:
        for idx in title_piece_indexes:
            if str(pieces[idx].get("text", "")).strip() == canonical_title_text:
                title_indexes_to_keep.add(idx)
                break

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

    def raw_html_has_callout_boundary(raw_html: str) -> bool:
        return bool(re.search(r"<(hr|h[1-6]|ul|ol)\b", raw_html, flags=re.IGNORECASE))

    def has_boundary_between(prev_idx: int, current_idx: int) -> bool:
        for piece_between in pieces[prev_idx + 1:current_idx]:
            if piece_between.get("kind") == "raw":
                if raw_html_has_callout_boundary(str(piece_between.get("html", ""))):
                    return True
            elif piece_between.get("kind") == "p" and piece_between.get("has_structural"):
                return True
        return False

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
            prev_idx = visible_paragraph_indexes[pos - 1]
            prev_piece = pieces[prev_idx]
            prev_text = str(prev_piece.get("text", ""))
            if prev_text.endswith(":") and not has_boundary_between(prev_idx, idx):
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

        class_list = set(piece.get("class_list", []))
        if "title" in class_list and idx not in title_indexes_to_keep:
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


def render_document_page(raw_html: str, pdf_href: str, doc_title: str, metadata: dict[str, object]) -> str:
    normalized = normalize_exported_html(raw_html)
    exported_styles = extract_head_styles(normalized)
    body_html = refine_body_html(extract_body_inner_html(normalized))

    slug = str(metadata["slug"])
    depth = len([part for part in slug.split("/") if part])
    home_href = "../" * (depth + 1)

    template = load_template("document_shell.html")
    return render_template(
        template,
        {
            "PAGE_TITLE": safe_text(f"{doc_title} | {SITE_NAME}"),
            "PAGE_DESCRIPTION": safe_text(str(metadata["description"])),
            "SITE_NAME": safe_text(SITE_NAME),
            "HOME_HREF": home_href,
            "PDF_HREF": safe_text(pdf_href),
            "CANONICAL_URL": safe_text(str(metadata["html_url"])),
            "STRUCTURED_DATA_JSON": build_structured_data(metadata),
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


def render_discovery_links(items: list[dict[str, object]], label: str) -> str:
    if not items:
        return ""

    links: list[str] = []
    for item in items:
        links.append(
            '<li class="pse-discovery-item">'
            f'<a href="{safe_text(str(item["html_path"]))}">{safe_text(str(item["title"]))}</a>'
            f'<span class="pse-discovery-kind">{safe_text(str(item["kind_label"]))}</span>'
            '</li>'
        )

    return (
        '<section class="pse-discovery">'
        f"<h2>{safe_text(label)}</h2>"
        '<ul class="pse-discovery-list">'
        + "".join(links)
        + "</ul>"
        "</section>"
    )


def inject_discovery_markup(html_text: str, references_html: str, related_html: str) -> str:
    discovery_html = references_html + related_html
    if not discovery_html:
        return html_text

    marker = "</main>"
    if marker in html_text:
        return html_text.replace(marker, discovery_html + "\n  </main>", 1)

    marker = '<footer class="pse-footer">'
    if marker in html_text:
        return html_text.replace(marker, discovery_html + "\n  " + marker, 1)

    return html_text + discovery_html


def build_version_relations(metadata_index: list[dict[str, object]]) -> dict[str, dict[str, object]]:
    families: dict[str, list[dict[str, object]]] = {}
    for item in metadata_index:
        family_key = str(item.get("family_key", "") or "")
        version_tuple = tuple(item.get("version_tuple", []))
        if not family_key or not version_tuple:
            continue
        families.setdefault(family_key, []).append(item)

    relations: dict[str, dict[str, object]] = {}
    for family_key, docs in families.items():
        docs_sorted = sorted(
            docs,
            key=lambda d: (
                tuple(d.get("version_tuple", [])),
                str(d.get("title", "")).lower(),
                str(d.get("slug", "")),
            ),
            reverse=True,
        )
        if not docs_sorted:
            continue
        latest = docs_sorted[0]
        latest_slug = str(latest["slug"])

        for idx, doc in enumerate(docs_sorted):
            slug = str(doc["slug"])
            newer = docs_sorted[:idx]
            older = docs_sorted[idx + 1:]
            relations[slug] = {
                "family_key": family_key,
                "latest_slug": latest_slug,
                "is_latest": slug == latest_slug,
                "newer": newer,
                "older": older,
            }
    return relations


def render_version_sections(relation: dict[str, object] | None) -> str:
    if not relation:
        return ""

    pieces: list[str] = []

    newer = relation.get("newer", [])
    if newer:
        newest = newer[0]
        pieces.append(
            '<section class="pse-discovery">'
            '<h2>Version status</h2>'
            '<ul class="pse-discovery-list">'
            '<li class="pse-discovery-item">'
            f'Newer version available: <a href="{safe_text(str(newest["html_path"]))}">{safe_text(str(newest["title"]))}</a>'
            '</li>'
            '</ul>'
            '</section>'
        )

    older = relation.get("older", [])
    if older:
        links = []
        for item in older[:3]:
            links.append(
                '<li class="pse-discovery-item">'
                f'<a href="{safe_text(str(item["html_path"]))}">{safe_text(str(item["title"]))}</a>'
                '</li>'
            )
        pieces.append(
            '<section class="pse-discovery">'
            '<h2>Older versions</h2>'
            '<ul class="pse-discovery-list">'
            + "".join(links) +
            '</ul>'
            '</section>'
        )

    return "".join(pieces)


def explicit_reference_match(source_ctx: dict[str, object], target_ctx: dict[str, object]) -> bool:
    norm_text = str(source_ctx["norm_text"])
    title_phrase = str(target_ctx["title_phrase"])

    if len(title_phrase) >= 16 and title_phrase in norm_text:
        return True

    for phrase in target_ctx["slug_phrases"]:
        if phrase and phrase in norm_text:
            return True

    version = str(target_ctx.get("version", ""))
    title_tokens = list(target_ctx.get("title_tokens", []))
    if version and version in norm_text:
        matched = sum(1 for token in title_tokens if token in norm_text)
        if matched >= 2:
            return True

    return False


def related_score(
    source_meta: dict[str, object],
    source_ctx: dict[str, object],
    target_meta: dict[str, object],
    target_ctx: dict[str, object],
    explicit_ref: bool,
) -> int:
    score = 0

    if explicit_ref:
        score += 100

    if source_meta.get("group_key") and source_meta.get("group_key") == target_meta.get("group_key"):
        score += 35

    if source_meta.get("content_type") == target_meta.get("content_type"):
        score += 10

    title_overlap = len(set(source_ctx["title_tokens"]) & set(target_ctx["title_tokens"]))
    desc_overlap = len(set(source_ctx["description_tokens"]) & set(target_ctx["description_tokens"]))

    score += min(25, title_overlap * 5)
    score += min(20, desc_overlap * 4)

    if source_meta.get("content_type") != target_meta.get("content_type"):
        pair = {str(source_meta.get("content_type")), str(target_meta.get("content_type"))}
        if pair in ({"papers", "contracts"}, {"papers", "replication"}):
            score += 5

    return score


def build_discovery_sections(
    metadata_index: list[dict[str, object]],
    contexts: dict[str, dict[str, object]],
) -> dict[str, tuple[str, str]]:
    results: dict[str, tuple[str, str]] = {}

    for item in metadata_index:
        source_slug = str(item["slug"])
        source_ctx = contexts[source_slug]

        references: list[dict[str, object]] = []
        related_candidates: list[tuple[int, dict[str, object], bool]] = []

        for target in metadata_index:
            target_slug = str(target["slug"])
            if target_slug == source_slug:
                continue

            target_ctx = contexts[target_slug]
            is_reference = explicit_reference_match(source_ctx, target_ctx)

            if is_reference:
                references.append(target)

            score = related_score(item, source_ctx, target, target_ctx, is_reference)
            related_candidates.append((score, target, is_reference))

        ref_seen: set[str] = set()
        ref_items: list[dict[str, object]] = []

        for target in sorted(references, key=lambda x: (str(x["title"]).lower(), str(x["slug"]))):
            target_slug = str(target["slug"])
            if target_slug in ref_seen:
                continue
            ref_seen.add(target_slug)
            ref_items.append(
                {
                    "title": target["title"],
                    "html_path": target["html_path"],
                    "kind_label": str(target["kind"]).replace("-", " ").title(),
                }
            )

        related_candidates.sort(key=lambda row: (-row[0], str(row[1]["title"]).lower(), str(row[1]["slug"])))
        related_items: list[dict[str, object]] = []
        related_seen: set[str] = set(ref_seen)

        for score, target, _is_reference in related_candidates:
            if score < 35:
                continue
            target_slug = str(target["slug"])
            if target_slug in related_seen:
                continue
            related_seen.add(target_slug)
            related_items.append(
                {
                    "title": target["title"],
                    "html_path": target["html_path"],
                    "kind_label": str(target["kind"]).replace("-", " ").title(),
                }
            )
            if len(related_items) >= 2:
                break

        results[source_slug] = (
            render_discovery_links(ref_items, "Referenced artifacts"),
            render_discovery_links(related_items, "Read next"),
        )

    return results


def inject_discovery_sections(
    dist_root: Path,
    metadata_index: list[dict[str, object]],
    contexts: dict[str, dict[str, object]],
) -> None:
    discovery_sections = build_discovery_sections(metadata_index, contexts)
    version_relations = build_version_relations(metadata_index)

    for item in metadata_index:
        source_slug = str(item["slug"])
        references_html, related_html = discovery_sections.get(source_slug, ("", ""))
        version_html = render_version_sections(version_relations.get(source_slug))

        out_path = dist_root / str(item["content_type"]) / Path(source_slug) / "index.html"
        if not out_path.exists():
            continue

        html_text = out_path.read_text(encoding="utf-8")
        html_text = inject_discovery_markup(html_text, version_html + references_html, related_html)
        out_path.write_text(html_text, encoding="utf-8")



def relative_href(from_dir: str, target_path: str) -> str:
    base = Path(from_dir.strip('/')) if from_dir.strip('/') else Path('.')
    rel = os.path.relpath('/' + target_path.strip('/'), '/' + str(base).strip('/'))
    return rel.replace(os.sep, '/')


def document_generated_description(body_html: str, doc_title: str) -> str:
    paragraphs = extract_candidate_paragraph_texts(body_html)
    description = derive_description(paragraphs, doc_title).strip()
    fallback = f"{doc_title} — published in {SITE_NAME}."
    if not description or description == fallback:
        return ''
    return description


def family_slug_and_version(entry: dict[str, str]) -> tuple[str, tuple[int, ...]]:
    family_key, _version, version_tuple = slug_family_info(entry["slug"])
    return family_key, version_tuple


def latest_entries_and_families(entries: list[dict[str, str]]) -> tuple[list[dict[str, str]], dict[tuple[str,str], list[dict[str, str]]]]:
    family_buckets: dict[tuple[str, str], list[dict[str, str]]] = {}
    passthrough: list[dict[str, str]] = []
    for entry in entries:
        family_key, version_tuple = family_slug_and_version(entry)
        if not family_key or not version_tuple:
            passthrough.append(entry)
            continue
        family_buckets.setdefault((entry["type"], family_key), []).append(entry)
    latest_only: list[dict[str, str]] = list(passthrough)
    for key, bucket in family_buckets.items():
        bucket_sorted = sorted(bucket, key=lambda e: (family_slug_and_version(e)[1], e['title'].lower(), e['slug']), reverse=True)
        family_buckets[key] = bucket_sorted
        latest_only.append(bucket_sorted[0])
    return latest_only, family_buckets


def render_redirect_page(target_href: str) -> str:
    template = load_template("redirect.html")
    return render_template(template, {"TARGET_HREF": safe_text(target_href), "SITE_NAME": safe_text(SITE_NAME)})


def build_doc(
    type_name: str,
    doc_dir: Path,
    relative_slug: str,
    tmp_root: Path,
) -> tuple[dict[str, str], dict[str, object], dict[str, object]]:
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
    normalized = normalize_exported_html(raw_html)
    body_html = refine_body_html(extract_body_inner_html(normalized))
    metadata, match_context = derive_document_metadata(type_name, relative_slug, doc_title, pdf.name, body_html)
    wrapped_html = render_document_page(raw_html, pdf_href, doc_title, metadata)
    (out_dir / "index.html").write_text(wrapped_html, encoding="utf-8")
    shutil.copy2(pdf, out_dir / pdf.name)

    return (
        {
            "type": type_name,
            "slug": slug,
            "pdf_name": pdf.name,
            "title": pdf.stem,
            "url": f"/{type_name}/{slug}/",
            "pdf_url": f"/{type_name}/{slug}/{pdf.name}",
            "description": document_generated_description(body_html, pdf.stem),
        },
        metadata,
        match_context,
    )


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
                "pdf_url": f"/contracts/{slug}/{pdf.name}",
                "pdf_only": "true",
                "description": "",
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
        title_html = f'<a class="item-title-link" href="{safe_text(primary_href)}">{safe_text(item["title"])}' + '</a>'
    else:
        title_html = safe_text(item["title"])
    description = (item.get("description") or "").strip()
    desc_html = f'<div class="item-description">{safe_text(description)}</div>' if description else ''
    latest_badge = '<span class="item-badge">Latest</span>' if item.get("is_latest") == "true" else ''
    version_note = '<span class="item-version-note">Older version</span>' if item.get("is_latest") == "false" else ''
    return ('<li class="archive-item">' f'<div class="item-title">{title_html}{latest_badge}{version_note}</div>' f'{desc_html}' f'<div class="item-actions">{meta}</div>' '</li>')


def render_family_block(family_label: str, latest_item: dict[str, str], all_items: list[dict[str, str]], mode: str) -> str:
    items = []
    if mode == 'latest':
        row = dict(latest_item)
        row['is_latest'] = 'true'
        items = [row]
    else:
        for idx, item in enumerate(all_items):
            row = dict(item)
            row['is_latest'] = 'true' if idx == 0 else 'false'
            items.append(row)
    rendered_items = ''.join(render_item_card(item) for item in items)
    heading = f'<h3>{safe_text(family_label)}</h3>' if family_label else ''
    return '<section class="group-block">' + heading + '<ul class="archive-list">' + rendered_items + '</ul></section>'


def render_sections(items: list[dict[str, str]], family_buckets: dict[tuple[str, str], list[dict[str, str]]], type_name: str, mode: str, empty_label: str) -> str:
    source_items = items if mode == 'latest' else [e for e in items if e['type'] == type_name]
    if not source_items:
        return f'<div class="empty-state">{safe_text(empty_label)}</div>'
    flat_items = []
    family_latest: dict[str, dict[str, str]] = {}
    for item in source_items:
        family_key, version_tuple = family_slug_and_version(item)
        if family_key and version_tuple:
            family_latest[family_key] = item
        else:
            flat_items.append(item)
    blocks: list[str] = []
    if flat_items:
        rendered_items = ''.join(render_item_card(dict(item, is_latest='true')) for item in sorted(flat_items, key=lambda x: x['title'].lower()))
        blocks.append('<section class="group-block"><ul class="archive-list">' + rendered_items + '</ul></section>')
    for family_key in sorted(family_latest):
        latest_item = family_latest[family_key]
        all_items = family_buckets.get((type_name, family_key), [latest_item])
        family_label = humanize_slug(family_key.split('/')[-1])
        blocks.append(render_family_block(family_label, latest_item, all_items, mode))
    return "\n".join(blocks)


def render_listing_page(entries: list[dict[str, str]], family_buckets: dict[tuple[str, str], list[dict[str, str]]], mode: str) -> str:
    grouped: dict[str, list[dict[str, str]]] = {k: [] for k in CONTENT_TYPES}
    source_entries = entries if mode == 'latest' else [e for e in entries]
    for entry in source_entries:
        grouped[entry['type']].append(entry)
    template = load_template('listing.html')
    title = 'Latest' if mode == 'latest' else 'Archive'
    intro = 'Current latest artifacts across papers, contracts, and replication materials.' if mode == 'latest' else 'Full archive with latest versions and prior version lineage grouped sanely.'
    home_href = '../' if mode in ('latest','archive') else './'
    latest_href = './' if mode == 'latest' else '../latest/'
    archive_href = './' if mode == 'archive' else '../archive/'
    return render_template(template, {'SITE_NAME': safe_text(SITE_NAME), 'PAGE_TITLE': safe_text(f'{title} | {SITE_NAME}'), 'PAGE_HEADING': safe_text(title), 'PAGE_INTRO': safe_text(intro), 'HOME_HREF': home_href, 'LATEST_HREF': latest_href, 'ARCHIVE_HREF': archive_href, 'PAPERS_SECTIONS': render_sections(grouped['papers'], family_buckets, 'papers', mode, 'No papers yet.'), 'CONTRACTS_SECTIONS': render_sections(grouped['contracts'], family_buckets, 'contracts', mode, 'No contracts yet.'), 'REPLICATION_SECTIONS': render_sections(grouped['replication'], family_buckets, 'replication', mode, 'No replication materials yet.')})


def render_home_page(latest_entries: list[dict[str, str]]) -> str:
    grouped: dict[str, list[dict[str, str]]] = {k: [] for k in CONTENT_TYPES}
    for entry in latest_entries:
        grouped[entry['type']].append(entry)
    template = load_template('home.html')
    return render_template(template, {'SITE_NAME': safe_text(SITE_NAME), 'LATEST_HREF': './latest/', 'ARCHIVE_HREF': './archive/', 'PAPERS_COUNT': str(len(grouped['papers'])), 'CONTRACTS_COUNT': str(len(grouped['contracts'])), 'REPLICATION_COUNT': str(len(grouped['replication']))})


def write_family_redirects(dist_root: Path, family_buckets: dict[tuple[str, str], list[dict[str, str]]]) -> None:
    for (type_name, family_key), bucket in family_buckets.items():
        target = bucket[0]
        out_dir = dist_root / type_name / Path(family_key)
        out_dir.mkdir(parents=True, exist_ok=True)
        target_href = relative_href(f'/{type_name}/{family_key}/', f'/{type_name}/{target["slug"]}/')
        (out_dir / 'index.html').write_text(render_redirect_page(target_href), encoding='utf-8')


def inject_discovery_sections(dist_root: Path, metadata_index: list[dict[str, object]], contexts: dict[str, dict[str, object]]) -> None:
    discovery_sections = build_discovery_sections(metadata_index, contexts)
    version_relations = build_version_relations(metadata_index)
    for item in metadata_index:
        source_slug = str(item['slug'])
        references_html, related_html = discovery_sections.get(source_slug, ('', ''))
        relation = version_relations.get(source_slug)
        footer_html = ''
        if relation and not relation.get('is_latest'):
            family_key = str(relation.get('family_key', ''))
            family_href = relative_href(f'/{item["content_type"]}/{source_slug}/', f'/{item["content_type"]}/{family_key}/')
            footer_html = '<section class="pse-discovery"><h2>Version status</h2><ul class="pse-discovery-list"><li class="pse-discovery-item">This is not the latest version. <a href="' + safe_text(family_href) + '">See the latest.</a></li></ul></section>'
        out_path = dist_root / str(item['content_type']) / Path(source_slug) / 'index.html'
        if not out_path.exists():
            continue
        html_text = out_path.read_text(encoding='utf-8')
        html_text = inject_discovery_markup(html_text, footer_html + references_html, related_html)
        out_path.write_text(html_text, encoding='utf-8')
def main() -> int:
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True, exist_ok=True)

    tmp_root = ROOT / ".build_tmp"
    if tmp_root.exists():
        shutil.rmtree(tmp_root)
    tmp_root.mkdir(parents=True, exist_ok=True)

    entries: list[dict[str, str]] = []
    metadata_index: list[dict[str, object]] = []
    match_contexts: dict[str, dict[str, object]] = {}

    try:
        for type_name in CONTENT_TYPES:
            type_root = INCOMING / type_name
            if not type_root.exists():
                continue
            if not type_root.is_dir():
                fail(f"{type_root} exists but is not a directory")

            for doc_dir, relative_slug in discover_doc_dirs(type_root):
                entry, metadata, match_context = build_doc(type_name, doc_dir, relative_slug, tmp_root)
                entries.append(entry)
                metadata_index.append(metadata)
                match_contexts[str(metadata["slug"])] = match_context

        entries = collect_pdf_only_contract_entries(entries)

        latest_entries, family_buckets = latest_entries_and_families(entries)
        (DIST / 'index.html').write_text(render_home_page(latest_entries), encoding='utf-8')
        latest_dir = DIST / 'latest'
        latest_dir.mkdir(parents=True, exist_ok=True)
        (latest_dir / 'index.html').write_text(render_listing_page(latest_entries, family_buckets, 'latest'), encoding='utf-8')
        archive_dir = DIST / 'archive'
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / 'index.html').write_text(render_listing_page(entries, family_buckets, 'archive'), encoding='utf-8')
        write_family_redirects(DIST, family_buckets)
        inject_discovery_sections(DIST, metadata_index, match_contexts)
        write_site_metadata_index(DIST, entries, metadata_index)
        write_sitemap(DIST, entries)
        write_build_manifest(DIST)
        print(f"Built archive into {DIST}")
        return 0
    finally:
        if tmp_root.exists():
            shutil.rmtree(tmp_root)


if __name__ == "__main__":
    raise SystemExit(main())
