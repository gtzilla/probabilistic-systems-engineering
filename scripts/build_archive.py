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

from archive_build.html_processing import (
    extract_body_inner_html,
    extract_candidate_paragraph_texts,
    extract_head_styles,
    normalize_exported_html,
    refine_body_html,
    strip_tags_to_text,
)
from archive_build.collections import (
    render_authority_collection_landing,
    render_authority_section_body,
    render_collection_navigation,
    render_non_engineering_collection_landing,
    split_authority_collection,
    split_non_engineering_collection,
)
from archive_build.non_engineering import (
    enhance_non_engineering_body_html,
    infer_non_engineering_theme,
)
from archive_build.listing_render import (
    render_home_page,
    render_listing_page,
    render_redirect_page,
)
from archive_build.discovery import (
    document_match_context,
    inject_discovery_markup,
    inject_discovery_sections,
    write_recommendation_index,
)

ROOT = Path(__file__).resolve().parents[1]
INCOMING = ROOT / "incoming"
DIST = ROOT / "dist"
TEMPLATES = ROOT / "scripts" / "templates"
SITE_NAME = "Probabilistic Systems Engineering"
SITE_URL = "https://ai.gtzilla.com"
CONTENT_TYPES = ["authority", "papers", "contracts", "replication", "non-engineering"]
TYPE_LABELS = {"authority": "Authority", "papers": "Papers", "contracts": "Contracts", "replication": "Replication & Verification", "non-engineering": "Non-Engineering"}


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
    if type_name == "non-engineering":
        return ("non-engineering-essay", "Article")
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

def render_document_page(raw_html: str, pdf_href: str, doc_title: str, metadata: dict[str, object]) -> str:
    normalized = normalize_exported_html(raw_html)
    exported_styles = extract_head_styles(normalized)
    raw_body_html = extract_body_inner_html(normalized)
    body_html = refine_body_html(raw_body_html)

    slug = str(metadata["slug"])
    depth = len([part for part in slug.split("/") if part])
    home_href = "../" * (depth + 1)

    template_name = "document_shell.html"
    non_engineering_theme = 'default'
    if str(metadata.get("content_type")) == "non-engineering":
        template_name = "document_shell_non_engineering.html"
        body_html = enhance_non_engineering_body_html(body_html)
        non_engineering_theme = infer_non_engineering_theme(metadata, doc_title)

    template = load_template(template_name)
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
            "NON_ENGINEERING_THEME": safe_text(non_engineering_theme),
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
            collection_items.append({'slug': section_slug, 'title': section_title, 'href': section_href, 'meta_slug': section_rel_slug})
            metadata_items.append(section_metadata)
            match_contexts[str(section_metadata['slug'])] = section_context

        for idx, section in enumerate(collection_items):
            section_slug = str(section['slug'])
            section_rel_slug = str(section['meta_slug'])
            section_out_dir = DIST / type_name / Path(section_rel_slug)
            section_out_dir.mkdir(parents=True, exist_ok=True)
            section_meta = next(item for item in metadata_items if str(item['slug']) == section_rel_slug)
            prev_slug = collection_items[idx - 1]['meta_slug'] if idx > 0 else ''
            next_slug = collection_items[idx + 1]['meta_slug'] if idx + 1 < len(collection_items) else ''
            section_meta['collection_prev_slug'] = prev_slug
            section_meta['collection_next_slug'] = next_slug
            section_meta['collection_index'] = idx + 1
            section_meta['collection_size'] = len(collection_items)
            section_meta['collection_title'] = doc_title
            section_body_html = render_authority_section_body(str(section['title']), sections[idx]['body_html'])
            section_href = f"/{type_name}/{section_rel_slug}/"
            essay_wrapped = render_document_page(raw_html, relative_href(section_href, metadata['pdf_path']), str(section['title']), section_meta)
            essay_html = essay_wrapped.replace(body_html, section_body_html, 1) if body_html in essay_wrapped else essay_wrapped
            essay_html = inject_discovery_markup(essay_html, [render_collection_navigation(doc_title, relative_href(section_href, collection_href), collection_items, section_slug)])
            (section_out_dir / 'index.html').write_text(essay_html, encoding='utf-8')

        entries[0]['description'] = f"Authority essay collection with {len(collection_items)} linked essays." if collection_items else "Authority collection landing page."
        entries[0]['essay_count'] = str(len(collection_items))
        entries[0]['essay_items'] = [{'title': item['title'], 'href': item['href']} for item in collection_items]
        landing_body_html = render_authority_collection_landing(doc_title, str(metadata.get('description', '')), collection_items)
        wrapped_html = wrapped_html.replace(body_html, landing_body_html, 1) if body_html in wrapped_html else wrapped_html

    elif type_name == "non-engineering":
        sections = split_non_engineering_collection(body_html)
        collection_items = []
        collection_href = f"/{type_name}/{slug}/"
        rendered_root_body_html = enhance_non_engineering_body_html(body_html)

        for section in sections:
            section_slug = section['slug']
            section_title = section['title']
            section_rel_slug = f"{relative_slug}/{section_slug}"
            section_metadata, section_context = derive_document_metadata(type_name, section_rel_slug, section_title, pdf.name, section['body_html'])
            section_metadata['kind'] = 'non-engineering-page'
            section_metadata['schema_type'] = 'Article'
            section_metadata['group_key'] = relative_slug.split('/')[0] if '/' in relative_slug else relative_slug
            section_metadata['family_key'] = ''
            section_metadata['version'] = ''
            section_metadata['version_tuple'] = []
            section_metadata['pdf_path'] = metadata['pdf_path']
            section_metadata['pdf_url'] = metadata['pdf_url']
            section_href = f"/{type_name}/{section_rel_slug}/"
            collection_items.append({'slug': section_slug, 'title': section_title, 'href': section_href, 'meta_slug': section_rel_slug})
            metadata_items.append(section_metadata)
            match_contexts[str(section_metadata['slug'])] = section_context

        for idx, section in enumerate(sections):
            section_slug = section['slug']
            section_title = section['title']
            section_rel_slug = f"{relative_slug}/{section_slug}"
            section_out_dir = DIST / type_name / Path(section_rel_slug)
            section_out_dir.mkdir(parents=True, exist_ok=True)
            section_body_html = enhance_non_engineering_body_html(section['body_html'])
            section_meta = next(item for item in metadata_items if str(item['slug']) == section_rel_slug)
            prev_slug = collection_items[idx - 1]['meta_slug'] if idx > 0 else ''
            next_slug = collection_items[idx + 1]['meta_slug'] if idx + 1 < len(collection_items) else ''
            section_meta['collection_prev_slug'] = prev_slug
            section_meta['collection_next_slug'] = next_slug
            section_meta['collection_index'] = idx + 1
            section_meta['collection_size'] = len(collection_items)
            section_meta['collection_title'] = doc_title
            section_href = f"/{type_name}/{section_rel_slug}/"
            section_wrapped = render_document_page(raw_html, relative_href(section_href, metadata['pdf_path']), section_title, section_meta)
            section_wrapped = section_wrapped.replace(rendered_root_body_html, section_body_html, 1) if rendered_root_body_html in section_wrapped else section_wrapped
            nav_html = render_collection_navigation(doc_title, relative_href(section_href, collection_href), collection_items, section_slug, 'Page')
            section_wrapped = inject_discovery_markup(section_wrapped, [nav_html])
            (section_out_dir / 'index.html').write_text(section_wrapped, encoding='utf-8')

        entries[0]['description'] = f"Non-engineering guide with {len(collection_items)} linked pages." if collection_items else "Non-engineering guide landing page."
        entries[0]['section_count'] = str(len(collection_items))
        entries[0]['section_items'] = [{'title': item['title'], 'href': item['href']} for item in collection_items]
        landing_body_html = render_non_engineering_collection_landing(doc_title, str(metadata.get('description', '')), collection_items)
        wrapped_html = wrapped_html.replace(rendered_root_body_html, landing_body_html, 1) if rendered_root_body_html in wrapped_html else wrapped_html

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


def write_family_redirects(dist_root: Path, family_buckets: dict[tuple[str, str], list[dict[str, str]]]) -> None:
    for (type_name, family_key), bucket in family_buckets.items():
        target = bucket[0]
        out_dir = dist_root / type_name / Path(family_key)
        out_dir.mkdir(parents=True, exist_ok=True)
        target_href = relative_href(f'/{type_name}/{family_key}/', f'/{type_name}/{target["slug"]}/')
        (out_dir / 'index.html').write_text(render_redirect_page(target_href, load_template, render_template, SITE_NAME), encoding='utf-8')


def write_non_engineering_root_redirect(dist_root: Path) -> None:
    out_dir = dist_root / 'non-engineering'
    out_dir.mkdir(parents=True, exist_ok=True)
    target_href = relative_href('/non-engineering/', '/non-engineering/what-AI-gets-wrong-when-you-iterate/')
    (out_dir / 'index.html').write_text(render_redirect_page(target_href, load_template, render_template, SITE_NAME), encoding='utf-8')


def copy_static_assets() -> None:
    assets_root = INCOMING / "assets"
    if not assets_root.exists():
        return
    if not assets_root.is_dir():
        fail(f"{assets_root} exists but is not a directory")
    dest_root = DIST / "assets"
    dest_root.mkdir(parents=True, exist_ok=True)
    for child in assets_root.iterdir():
        dest = dest_root / child.name
        if child.is_dir():
            shutil.copytree(child, dest, dirs_exist_ok=True)
        else:
            shutil.copy2(child, dest)





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
        copy_static_assets()
        latest_entries, family_buckets = latest_entries_and_families(entries)
        (DIST / 'index.html').write_text(render_home_page(latest_entries, CONTENT_TYPES, SITE_NAME, load_template, render_template), encoding='utf-8')
        latest_dir = DIST / 'latest'
        latest_dir.mkdir(parents=True, exist_ok=True)
        (latest_dir / 'index.html').write_text(render_listing_page(latest_entries, family_buckets, 'latest', CONTENT_TYPES, SITE_NAME, load_template, render_template), encoding='utf-8')
        archive_dir = DIST / 'archive'
        archive_dir.mkdir(parents=True, exist_ok=True)
        (archive_dir / 'index.html').write_text(render_listing_page(entries, family_buckets, 'archive', CONTENT_TYPES, SITE_NAME, load_template, render_template), encoding='utf-8')
        write_family_redirects(DIST, family_buckets)
        write_non_engineering_root_redirect(DIST)
        recommendation_artifacts = inject_discovery_sections(
            DIST, metadata_index, match_contexts, TYPE_LABELS, safe_text, relative_href
        )
        write_site_metadata_index(DIST, entries, metadata_index)
        write_recommendation_index(DIST, recommendation_artifacts, SITE_NAME, SITE_URL)
        write_sitemap(DIST, entries)
        write_build_manifest(DIST)
        print(f"Built archive into {DIST}")
        return 0
    finally:
        if tmp_root.exists():
            shutil.rmtree(tmp_root)


if __name__ == "__main__":
    raise SystemExit(main())
