#!/usr/bin/env python3
from __future__ import annotations

from collections import Counter, defaultdict

import hashlib
import html
import json
import math
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
CONTENT_TYPES = ["authority", "papers", "contracts", "replication"]
TYPE_LABELS = {"authority": "Authority", "papers": "Results", "contracts": "Engineering", "replication": "Replication & Verification"}


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
    if type_name == "authority":
        return ("authority-essay-collection", "Book")
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


def recommendation_source_text(metadata: dict[str, object], full_text: str) -> str:
    title = str(metadata.get("title", "")).strip()
    description = str(metadata.get("description", "")).strip()
    kind = str(metadata.get("kind", "")).replace("-", " ")
    content_type = str(metadata.get("content_type", "")).replace("-", " ")
    group_key = str(metadata.get("group_key", "")).replace("-", " ")
    family_key = str(metadata.get("family_key", "")).split("/")[-1].replace("-", " ")
    parts = [title, title, description, kind, content_type, group_key, family_key, full_text]
    return " ".join(part for part in parts if part)


def document_match_context(metadata: dict[str, object], full_text: str) -> dict[str, object]:
    title = str(metadata["title"])
    description = str(metadata.get("description", ""))
    slug = str(metadata["slug"])
    version = str(metadata.get("version", ""))
    title_tokens = unique_preserve_order(significant_tokens(title))
    description_tokens = unique_preserve_order(significant_tokens(description))
    recommendation_text = recommendation_source_text(metadata, full_text)
    recommendation_tokens = significant_tokens(recommendation_text)
    return {
        "norm_text": normalize_for_match(full_text),
        "title_phrase": normalize_for_match(title),
        "slug_phrases": slug_reference_phrases(slug),
        "title_tokens": title_tokens,
        "description_tokens": description_tokens,
        "version": version.lower(),
        "recommendation_text": recommendation_text,
        "recommendation_tokens": recommendation_tokens,
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


def compute_tfidf_vectors(contexts: dict[str, dict[str, object]]) -> dict[str, dict[str, float]]:
    doc_tokens: dict[str, list[str]] = {}
    document_frequency: dict[str, int] = defaultdict(int)

    for slug, ctx in contexts.items():
        tokens = list(ctx.get("recommendation_tokens", []))
        doc_tokens[slug] = tokens
        for token in set(tokens):
            document_frequency[token] += 1

    total_docs = max(1, len(doc_tokens))
    idf: dict[str, float] = {}
    for token, df in document_frequency.items():
        idf[token] = math.log((1 + total_docs) / (1 + df)) + 1.0

    vectors: dict[str, dict[str, float]] = {}
    for slug, tokens in doc_tokens.items():
        if not tokens:
            vectors[slug] = {}
            continue

        counts = Counter(tokens)
        total_terms = sum(counts.values()) or 1
        vector: dict[str, float] = {}
        for token, count in counts.items():
            tf = count / total_terms
            vector[token] = tf * idf.get(token, 1.0)
        vectors[slug] = vector

    return vectors


def cosine_similarity_sparse(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    dot = sum(value * right.get(token, 0.0) for token, value in left.items())
    if dot <= 0.0:
        return 0.0
    left_norm = math.sqrt(sum(value * value for value in left.values()))
    right_norm = math.sqrt(sum(value * value for value in right.values()))
    if left_norm <= 0.0 or right_norm <= 0.0:
        return 0.0
    return dot / (left_norm * right_norm)


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
    raw_body_html = extract_body_inner_html(normalized)
    body_html = refine_body_html(raw_body_html)

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


def inject_discovery_markup(html_text: str, sections_html: list[str]) -> str:
    discovery_html = "".join(section for section in sections_html if section)
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
    target_meta: dict[str, object],
    similarity: float,
    explicit_ref: bool,
) -> float:
    score = similarity

    if explicit_ref:
        score += 0.22

    if source_meta.get("content_type") == target_meta.get("content_type"):
        score += 0.03

    if source_meta.get("group_key") and source_meta.get("group_key") == target_meta.get("group_key"):
        score += 0.05

    source_pair = {str(source_meta.get("content_type")), str(target_meta.get("content_type"))}
    if source_pair in ({"papers", "contracts"}, {"papers", "replication"}):
        score += 0.02

    if target_meta.get("content_type") == "replication" and source_meta.get("content_type") != "replication":
        score -= 0.08

    return score


def candidate_ineligible(
    source_meta: dict[str, object],
    target_meta: dict[str, object],
    target_relation: dict[str, object] | None,
) -> tuple[bool, str]:
    source_slug = str(source_meta["slug"])
    target_slug = str(target_meta["slug"])
    if source_slug == target_slug:
        return True, "same_document"

    source_family = str(source_meta.get("family_key", "") or "")
    target_family = str(target_meta.get("family_key", "") or "")
    if source_family and source_family == target_family:
        return True, "same_family"

    if target_relation and not bool(target_relation.get("is_latest")):
        return True, "not_latest_version"

    return False, ""


def pick_related_candidates(
    source_meta: dict[str, object],
    metadata_by_slug: dict[str, dict[str, object]],
    contexts: dict[str, dict[str, object]],
    tfidf_vectors: dict[str, dict[str, float]],
    version_relations: dict[str, dict[str, object]],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, str]]]:
    source_slug = str(source_meta["slug"])
    source_ctx = contexts[source_slug]
    source_vector = tfidf_vectors.get(source_slug, {})

    references: list[dict[str, object]] = []
    related_candidates: list[tuple[float, dict[str, object]]] = []
    replication_candidates: list[tuple[float, dict[str, object]]] = []
    debug_excluded: list[dict[str, str]] = []

    for target_slug, target_meta in metadata_by_slug.items():
        target_ctx = contexts[target_slug]
        explicit_ref = explicit_reference_match(source_ctx, target_ctx)
        if explicit_ref:
            references.append(target_meta)

        target_relation = version_relations.get(target_slug)
        ineligible, reason = candidate_ineligible(source_meta, target_meta, target_relation)
        if ineligible:
            debug_excluded.append({"docId": target_slug, "reason": reason})
            continue

        similarity = cosine_similarity_sparse(source_vector, tfidf_vectors.get(target_slug, {}))
        score = related_score(source_meta, target_meta, similarity, explicit_ref)

        if target_meta.get("content_type") == "replication":
            if score >= 0.12:
                replication_candidates.append((score, target_meta))
            continue

        if score >= 0.14:
            related_candidates.append((score, target_meta))

    ref_items: list[dict[str, object]] = []
    ref_seen: set[str] = set()
    for target in sorted(references, key=lambda x: (str(x["title"]).lower(), str(x["slug"]))):
        target_slug = str(target["slug"])
        if target_slug in ref_seen:
            continue
        ref_seen.add(target_slug)
        ref_items.append({
            "title": target["title"],
            "html_path": target["html_path"],
            "kind_label": TYPE_LABELS.get(str(target["content_type"]), str(target["kind"]).replace("-", " ").title()),
        })

    related_items: list[dict[str, object]] = []
    related_seen: set[str] = set(ref_seen)
    related_candidates.sort(key=lambda row: (-row[0], str(row[1]["title"]).lower(), str(row[1]["slug"])))
    for score, target in related_candidates:
        target_slug = str(target["slug"])
        if target_slug in related_seen:
            continue
        related_seen.add(target_slug)
        related_items.append({
            "title": target["title"],
            "html_path": target["html_path"],
            "kind_label": TYPE_LABELS.get(str(target["content_type"]), str(target["kind"]).replace("-", " ").title()),
            "score": round(score, 6),
            "slug": target_slug,
        })
        if len(related_items) >= 4:
            break

    read_next_items = related_items[:1]
    related_surface_items = related_items[1:4]

    verification_items: list[dict[str, object]] = []
    replication_candidates.sort(key=lambda row: (-row[0], str(row[1]["title"]).lower(), str(row[1]["slug"])))
    for score, target in replication_candidates[:2]:
        verification_items.append({
            "title": target["title"],
            "html_path": target["html_path"],
            "kind_label": TYPE_LABELS.get(str(target["content_type"]), str(target["kind"]).replace("-", " ").title()),
            "score": round(score, 6),
            "slug": str(target["slug"]),
        })

    return ref_items, read_next_items, related_surface_items, verification_items, debug_excluded


def build_discovery_sections(
    metadata_index: list[dict[str, object]],
    contexts: dict[str, dict[str, object]],
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, object]]]:
    version_relations = build_version_relations(metadata_index)
    tfidf_vectors = compute_tfidf_vectors(contexts)
    metadata_by_slug = {str(item["slug"]): item for item in metadata_index}

    rendered: dict[str, dict[str, str]] = {}
    recommendation_artifacts: dict[str, dict[str, object]] = {}

    for item in metadata_index:
        source_slug = str(item["slug"])
        references, read_next_items, related_items, verification_items, debug_excluded = pick_related_candidates(
            item, metadata_by_slug, contexts, tfidf_vectors, version_relations
        )

        rendered[source_slug] = {
            "references_html": render_discovery_links(references, "Referenced artifacts"),
            "read_next_html": render_discovery_links(read_next_items, "Read next"),
            "related_html": render_discovery_links(related_items, "Related"),
            "verification_html": render_discovery_links(verification_items, "Verification & replication"),
            "version_html": render_version_sections(version_relations.get(source_slug)),
        }

        recommendation_artifacts[source_slug] = {
            "docId": source_slug,
            "readNext": [item["slug"] for item in read_next_items],
            "related": [item["slug"] for item in related_items],
            "versionHistory": [str(v["slug"]) for v in version_relations.get(source_slug, {}).get("older", [])[:3]],
            "verification": [item["slug"] for item in verification_items],
            "debug": {"excluded": debug_excluded},
        }

    return rendered, recommendation_artifacts


def write_recommendation_index(dist_root: Path, recommendation_artifacts: dict[str, dict[str, object]]) -> None:
    metadata_dir = dist_root / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "site": SITE_NAME,
        "site_url": SITE_URL,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "recommendations": recommendation_artifacts,
    }
    (metadata_dir / "recommendations.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def inject_discovery_sections(
    dist_root: Path,
    metadata_index: list[dict[str, object]],
    contexts: dict[str, dict[str, object]],
) -> dict[str, dict[str, object]]:
    discovery_sections, recommendation_artifacts = build_discovery_sections(metadata_index, contexts)
    version_relations = build_version_relations(metadata_index)

    for item in metadata_index:
        source_slug = str(item["slug"])
        section_html = discovery_sections.get(source_slug, {})
        relation = version_relations.get(source_slug)
        footer_html = ""
        if relation and not relation.get("is_latest"):
            family_key = str(relation.get("family_key", ""))
            family_href = relative_href(f'/{item["content_type"]}/{source_slug}/', f'/{item["content_type"]}/{family_key}/')
            footer_html = '<section class="pse-discovery"><h2>Version status</h2><ul class="pse-discovery-list"><li class="pse-discovery-item">This is not the latest version. <a href="' + safe_text(family_href) + '">See the latest.</a></li></ul></section>'
        out_path = dist_root / str(item["content_type"]) / Path(source_slug) / 'index.html'
        if not out_path.exists():
            continue
        html_text = out_path.read_text(encoding='utf-8')
        html_text = inject_discovery_markup(html_text, [footer_html, section_html.get('version_html', ''), section_html.get('references_html', ''), section_html.get('read_next_html', ''), section_html.get('related_html', ''), section_html.get('verification_html', '')])
        out_path.write_text(html_text, encoding='utf-8')
    return recommendation_artifacts


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


def slugify_fragment(text: str) -> str:
    value = normalize_for_match(text).replace(' ', '-')
    value = re.sub(r'-+', '-', value).strip('-')
    return value or 'section'


def authority_title_blocks(body_html: str) -> list[tuple[int, int, str]]:
    excluded = {
        'cover',
        'authority execution and refusal',
        'authority is the power to refuse execution at the first irreversible side effect',
        'framing',
        'table of contents',
    }
    pattern = re.compile(r'<p\b(?P<attrs>[^>]*)class="(?P<classval>[^"]*\btitle\b[^"]*)"[^>]*>(?P<body>.*?)</p>', flags=re.IGNORECASE | re.DOTALL)
    blocks: list[tuple[int, int, str]] = []
    last_key = ''
    for match in pattern.finditer(body_html):
        title = strip_tags_to_text(match.group('body'))
        key = normalize_for_match(title)
        if not key or key in excluded:
            continue
        if key == last_key:
            continue
        last_key = key
        blocks.append((match.start(), match.end(), title))
    return blocks


def split_authority_collection(body_html: str) -> list[dict[str, str]]:
    blocks = authority_title_blocks(body_html)
    if not blocks:
        return []
    sections: list[dict[str, str]] = []
    for idx, (start, end, title) in enumerate(blocks):
        section_start = start
        section_end = blocks[idx + 1][0] if idx + 1 < len(blocks) else len(body_html)
        section_html = body_html[section_start:section_end].strip()
        if not section_html:
            continue
        sections.append({'title': title, 'slug': slugify_fragment(title), 'body_html': section_html})
    return sections


def render_collection_sections(items: list[dict[str, str]], current_slug: str = '') -> str:
    if not items:
        return ''
    rows: list[str] = []
    for idx, item in enumerate(items, start=1):
        href = safe_text(item['href'])
        title = safe_text(item['title'])
        current = ' <span class="pse-discovery-kind">Current</span>' if item.get('slug') == current_slug else ''
        rows.append('<li class="pse-discovery-item"><a href="' + href + '">' + str(idx) + '. ' + title + '</a>' + current + '</li>')
    return '<section class="pse-discovery"><h2>Collection essays</h2><ul class="pse-discovery-list">' + ''.join(rows) + '</ul></section>'


def render_collection_navigation(collection_title: str, collection_href: str, items: list[dict[str, str]], current_slug: str) -> str:
    if not items:
        return ''
    current_index = next((idx for idx, item in enumerate(items) if item.get('slug') == current_slug), -1)
    links = ['<li class="pse-discovery-item"><a href="' + safe_text(collection_href) + '">Back to ' + safe_text(collection_title) + '</a></li>']
    if current_index > 0:
        prev_item = items[current_index - 1]
        links.append('<li class="pse-discovery-item">Previous: <a href="' + safe_text(prev_item['href']) + '">' + safe_text(prev_item['title']) + '</a></li>')
    if 0 <= current_index < len(items) - 1:
        next_item = items[current_index + 1]
        links.append('<li class="pse-discovery-item">Next: <a href="' + safe_text(next_item['href']) + '">' + safe_text(next_item['title']) + '</a></li>')
    return '<section class="pse-discovery"><h2>Collection navigation</h2><ul class="pse-discovery-list">' + ''.join(links) + '</ul></section>'


def build_doc(
    type_name: str,
    doc_dir: Path,
    relative_slug: str,
    tmp_root: Path,
) -> tuple[list[dict[str, str]], list[dict[str, object]], dict[str, dict[str, object]]]:
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
    raw_body_html = extract_body_inner_html(normalized)
    body_html = refine_body_html(raw_body_html)
    metadata, match_context = derive_document_metadata(type_name, relative_slug, doc_title, pdf.name, body_html)
    wrapped_html = render_document_page(raw_html, pdf_href, doc_title, metadata)
    shutil.copy2(pdf, out_dir / pdf.name)

    entries = [{
        "type": type_name,
        "slug": slug,
        "pdf_name": pdf.name,
        "title": pdf.stem,
        "url": f"/{type_name}/{slug}/",
        "pdf_url": f"/{type_name}/{slug}/{pdf.name}",
        "description": document_generated_description(body_html, pdf.stem),
    }]
    metadata_items = [metadata]
    match_contexts = {str(metadata["slug"]): match_context}

    if type_name == "authority":
        sections = split_authority_collection(raw_body_html)
        collection_items = []
        collection_href = f"/{type_name}/{slug}/"
        for section in sections:
            section_slug = section['slug']
            section_title = section['title']
            section_rel_slug = f"{relative_slug}/{section_slug}"
            section_out_dir = DIST / type_name / Path(section_rel_slug)
            section_out_dir.mkdir(parents=True, exist_ok=True)
            section_body_html = refine_body_html(section['body_html'])
            section_metadata, section_context = derive_document_metadata(type_name, section_rel_slug, section_title, pdf.name, section_body_html)
            section_metadata['kind'] = 'authority-essay'
            section_metadata['schema_type'] = 'Article'
            section_metadata['group_key'] = relative_slug.split('/')[0] if '/' in relative_slug else relative_slug
            section_metadata['family_key'] = relative_slug
            section_metadata['version'] = metadata.get('version', '')
            section_metadata['version_tuple'] = list(metadata.get('version_tuple', []))
            section_metadata['pdf_path'] = metadata['pdf_path']
            section_metadata['pdf_url'] = metadata['pdf_url']
            section_href = f"/{type_name}/{section_rel_slug}/"
            collection_items.append({'slug': section_slug, 'title': section_title, 'href': section_href})
            essay_wrapped = render_document_page(raw_html, relative_href(section_href, metadata['pdf_path']), section_title, section_metadata)
            essay_html = essay_wrapped.replace(body_html, section_body_html, 1) if body_html in essay_wrapped else essay_wrapped
            essay_html = inject_discovery_markup(essay_html, [render_collection_navigation(doc_title, relative_href(section_href, collection_href), collection_items, section_slug)])
            (section_out_dir / 'index.html').write_text(essay_html, encoding='utf-8')
            metadata_items.append(section_metadata)
            match_contexts[str(section_metadata['slug'])] = section_context
        wrapped_html = inject_discovery_markup(wrapped_html, [render_collection_sections(collection_items)])

    (out_dir / "index.html").write_text(wrapped_html, encoding="utf-8")
    return entries, metadata_items, match_contexts


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
    intro = 'Current latest artifacts across authority, engineering, results, and replication surfaces.' if mode == 'latest' else 'Full archive with latest versions and prior version lineage grouped sanely.'
    home_href = '../' if mode in ('latest','archive') else './'
    latest_href = './' if mode == 'latest' else '../latest/'
    archive_href = './' if mode == 'archive' else '../archive/'
    return render_template(template, {'SITE_NAME': safe_text(SITE_NAME), 'PAGE_TITLE': safe_text(f'{title} | {SITE_NAME}'), 'PAGE_HEADING': safe_text(title), 'PAGE_INTRO': safe_text(intro), 'HOME_HREF': home_href, 'LATEST_HREF': latest_href, 'ARCHIVE_HREF': archive_href, 'AUTHORITY_SECTIONS': render_sections(grouped['authority'], family_buckets, 'authority', mode, 'No authority collections yet.'), 'PAPERS_SECTIONS': render_sections(grouped['papers'], family_buckets, 'papers', mode, 'No results yet.'), 'CONTRACTS_SECTIONS': render_sections(grouped['contracts'], family_buckets, 'contracts', mode, 'No engineering artifacts yet.'), 'REPLICATION_SECTIONS': render_sections(grouped['replication'], family_buckets, 'replication', mode, 'No replication materials yet.')})


def render_home_page(latest_entries: list[dict[str, str]]) -> str:
    grouped: dict[str, list[dict[str, str]]] = {k: [] for k in CONTENT_TYPES}
    for entry in latest_entries:
        grouped[entry['type']].append(entry)
    template = load_template('home.html')
    return render_template(template, {
        'SITE_NAME': safe_text(SITE_NAME),
        'LATEST_HREF': './latest/',
        'ARCHIVE_HREF': './archive/',
        'ENTRY_PAPER_HREF': './papers/is-this-engineering/',
        'AUTHORITY_COUNT': str(len(grouped['authority'])),
        'PAPERS_COUNT': str(len(grouped['papers'])),
        'CONTRACTS_COUNT': str(len(grouped['contracts'])),
        'REPLICATION_COUNT': str(len(grouped['replication'])),
    })


def write_family_redirects(dist_root: Path, family_buckets: dict[tuple[str, str], list[dict[str, str]]]) -> None:
    for (type_name, family_key), bucket in family_buckets.items():
        target = bucket[0]
        out_dir = dist_root / type_name / Path(family_key)
        out_dir.mkdir(parents=True, exist_ok=True)
        target_href = relative_href(f'/{type_name}/{family_key}/', f'/{type_name}/{target["slug"]}/')
        (out_dir / 'index.html').write_text(render_redirect_page(target_href), encoding='utf-8')


def inject_discovery_sections(dist_root: Path, metadata_index: list[dict[str, object]], contexts: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    discovery_sections, recommendation_artifacts = build_discovery_sections(metadata_index, contexts)
    version_relations = build_version_relations(metadata_index)
    for item in metadata_index:
        source_slug = str(item['slug'])
        section_html = discovery_sections.get(source_slug, {})
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
        html_text = inject_discovery_markup(html_text, [footer_html, section_html.get('version_html', ''), section_html.get('references_html', ''), section_html.get('read_next_html', ''), section_html.get('related_html', ''), section_html.get('verification_html', '')])
        out_path.write_text(html_text, encoding='utf-8')
    return recommendation_artifacts
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
                doc_entries, doc_metadata_items, doc_match_contexts = build_doc(type_name, doc_dir, relative_slug, tmp_root)
                entries.extend(doc_entries)
                metadata_index.extend(doc_metadata_items)
                match_contexts.update(doc_match_contexts)

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
        recommendation_artifacts = inject_discovery_sections(DIST, metadata_index, match_contexts)
        write_site_metadata_index(DIST, entries, metadata_index)
        write_recommendation_index(DIST, recommendation_artifacts)
        write_sitemap(DIST, entries)
        write_build_manifest(DIST)
        print(f"Built archive into {DIST}")
        return 0
    finally:
        if tmp_root.exists():
            shutil.rmtree(tmp_root)


if __name__ == "__main__":
    raise SystemExit(main())
