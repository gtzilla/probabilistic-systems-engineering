from __future__ import annotations

import html
import re

from archive_build.html_processing import refine_body_html, strip_tags_to_text


def safe_text(value: str) -> str:
    return html.escape(value, quote=True)


def normalize_for_match(text: str) -> str:
    lowered = html.unescape(text).lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def slugify_fragment(text: str) -> str:
    value = normalize_for_match(text).replace(" ", "-")
    value = re.sub(r"-+", "-", value).strip("-")
    return value or "section"


def authority_title_blocks(body_html: str) -> list[tuple[int, int, str]]:
    excluded = {
        "cover",
        "authority execution and refusal",
        "authority is the power to refuse execution at the first irreversible side effect",
        "framing",
        "table of contents",
    }
    pattern = re.compile(
        r'<p\b(?P<attrs>[^>]*)class="(?P<classval>[^"]*\btitle\b[^"]*)"[^>]*>(?P<body>.*?)</p>',
        flags=re.IGNORECASE | re.DOTALL,
    )
    blocks: list[tuple[int, int, str]] = []
    last_key = ""
    for match in pattern.finditer(body_html):
        title = strip_tags_to_text(match.group("body"))
        key = normalize_for_match(title)
        if not key or key in excluded or key == last_key:
            continue
        last_key = key
        blocks.append((match.start(), match.end(), title))
    return blocks


def first_h1_title(section_html: str) -> str:
    match = re.search(r"<h1\b[^>]*>(.*?)</h1>", section_html, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return strip_tags_to_text(match.group(1)).strip()


def authority_title_matches_canonical(candidate_title: str, canonical_title: str) -> bool:
    candidate_key = normalize_for_match(candidate_title)
    canonical_key = normalize_for_match(canonical_title)
    if not candidate_key or not canonical_key:
        return False
    if candidate_key == canonical_key:
        return True
    candidate_key = re.sub(r"\.\.\.$", "", candidate_key).strip()
    candidate_key = re.sub(r"\s+", " ", candidate_key).strip()
    canonical_key = re.sub(r"\s+", " ", canonical_key).strip()
    return bool(candidate_key) and canonical_key.startswith(candidate_key)


def strip_leading_authority_title_wrappers(section_html: str, canonical_title: str) -> str:
    remaining = section_html.lstrip()
    if not canonical_title.strip():
        return remaining

    title_pat = re.compile(
        r'^\s*<p\b(?P<attrs>[^>]*)class="(?P<classval>[^"]*\btitle\b[^"]*)"[^>]*>(?P<body>.*?)</p>',
        flags=re.IGNORECASE | re.DOTALL,
    )

    while True:
        match = title_pat.match(remaining)
        if not match:
            break
        candidate = strip_tags_to_text(match.group("body"))
        if not authority_title_matches_canonical(candidate, canonical_title):
            break
        remaining = remaining[match.end():].lstrip()
    return remaining


def split_authority_collection(body_html: str) -> list[dict[str, str]]:
    blocks = authority_title_blocks(body_html)
    if not blocks:
        return []
    sections: list[dict[str, str]] = []
    for idx, (start, _end, title) in enumerate(blocks):
        section_start = start
        section_end = blocks[idx + 1][0] if idx + 1 < len(blocks) else len(body_html)
        section_html = body_html[section_start:section_end].strip()
        if not section_html:
            continue
        canonical_title = first_h1_title(section_html) or title
        cleaned_body = strip_leading_authority_title_wrappers(section_html, canonical_title)
        sections.append(
            {
                "title": canonical_title,
                "slug": slugify_fragment(canonical_title),
                "body_html": cleaned_body,
            }
        )
    return sections


def split_non_engineering_collection(body_html: str) -> list[dict[str, str]]:
    pattern = re.compile(r"<h2\b[^>]*>.*?</h2>", flags=re.IGNORECASE | re.DOTALL)
    matches = list(pattern.finditer(body_html))
    raw_sections: list[dict[str, str]] = []
    for idx, match in enumerate(matches):
        title = strip_tags_to_text(match.group(0)).strip()
        if not title:
            continue
        section_start = match.start()
        section_end = matches[idx + 1].start() if idx + 1 < len(matches) else len(body_html)
        section_html = body_html[section_start:section_end].strip()
        if not section_html:
            continue
        raw_sections.append({
            "title": title,
            "slug": slugify_fragment(title),
            "body_html": section_html,
            "key": normalize_for_match(title),
        })

    if not raw_sections:
        return []

    overview_keys = {
        "the core finding",
        "the mechanism",
        "why this is not obvious",
        "the research behind this",
    }
    profile_keys = [
        "for designers",
        "for startup and growth stage executives",
        "for enterprise and public company executives",
    ]

    overview_parts = [section["body_html"] for section in raw_sections if section["key"] in overview_keys]
    sections: list[dict[str, str]] = []
    if overview_parts:
        sections.append({
            "title": "Start Here",
            "slug": "start-here",
            "body_html": "\n".join(overview_parts),
        })

    for key in profile_keys:
        for section in raw_sections:
            if section["key"] == key:
                sections.append({
                    "title": section["title"],
                    "slug": section["slug"],
                    "body_html": section["body_html"],
                })
                break

    for section in raw_sections:
        if section["key"] in overview_keys or section["key"] in profile_keys:
            continue
        sections.append({
            "title": section["title"],
            "slug": section["slug"],
            "body_html": section["body_html"],
        })

    return sections


def render_non_engineering_entry_children(item: dict[str, object]) -> str:
    section_items = item.get("section_items")
    if not section_items or not isinstance(section_items, list):
        return ""
    links: list[str] = []
    for section in section_items:
        if not isinstance(section, dict):
            continue
        href = safe_text(str(section.get("href", "")))
        title = safe_text(str(section.get("title", "")))
        if href and title:
            links.append(f'<li><a href="{href}">{title}</a></li>')
    if not links:
        return ""
    return '<div class="item-children"><div class="item-children-label">Guide pages</div><ul class="item-children-list">' + ''.join(links) + "</ul></div>"


def render_non_engineering_collection_sections(items: list[dict[str, str]], current_slug: str = "") -> str:
    if not items:
        return ""
    rows: list[str] = []
    for item in items:
        href = safe_text(item["href"])
        title = safe_text(item["title"])
        current = ' <span class="pse-discovery-kind">Current</span>' if item.get("slug") == current_slug else ""
        rows.append(f'<li class="pse-discovery-item"><a href="{href}">{title}</a>{current}</li>')
    return '<section><h2>Guide pages</h2><p>Start with the overview, then move into the audience-specific paths.</p><ul>' + ''.join(rows) + "</ul></section>"


def render_non_engineering_collection_landing(doc_title: str, description: str, items: list[dict[str, str]]) -> str:
    intro = safe_text(description).strip()
    intro_html = f"<p>{intro}</p>" if intro else ""
    count_label = f"{len(items)} pages" if items else "No pages detected yet."
    toc = render_non_engineering_collection_sections(items)
    return (
        '<section class="pse-authority-collection">'
        + f"<h1>{safe_text(doc_title)}</h1>"
        + '<p><strong>Non-engineering guide.</strong> Start with the overview, then move into the audience-specific paths for design, startup, or enterprise readers.</p>'
        + intro_html
        + f'<p><strong>Contents:</strong> {safe_text(count_label)}</p>'
        + toc
        + "</section>"
    )


def render_authority_section_body(section_title: str, section_body_html: str) -> str:
    refined_body = strip_leading_authority_title_wrappers(refine_body_html(section_body_html), section_title)
    while True:
        title_match = re.match(r'^\s*<h([1-3])\b[^>]*>(.*?)</h\1>', refined_body, flags=re.IGNORECASE | re.DOTALL)
        if not title_match:
            break
        candidate_title = strip_tags_to_text(title_match.group(2)).strip()
        if not authority_title_matches_canonical(candidate_title, section_title):
            break
        refined_body = refined_body[title_match.end():].lstrip()
    return (
        '<header class="pse-doc-header">'
        + '<p class="pse-lead-in">Authority, Execution, and Refusal</p>'
        + '<h1>' + safe_text(section_title) + '</h1>'
        + '</header>'
        + refined_body
    )


def render_collection_sections(items: list[dict[str, str]], current_slug: str = "") -> str:
    if not items:
        return ""
    rows: list[str] = []
    for idx, item in enumerate(items, start=1):
        href = safe_text(item["href"])
        title = safe_text(item["title"])
        current = ' <span class="pse-discovery-kind">Current</span>' if item.get("slug") == current_slug else ""
        rows.append(f'<li class="pse-discovery-item"><a href="{href}">{idx}. {title}</a>{current}</li>')
    return '<section><h2>Collection essays</h2><p>Read in order. Each essay builds on the last.</p><ol>' + ''.join(rows) + "</ol></section>"


def render_authority_entry_children(item: dict[str, object]) -> str:
    essay_items = item.get("essay_items")
    if not essay_items or not isinstance(essay_items, list):
        return ""
    links: list[str] = []
    for essay in essay_items:
        if not isinstance(essay, dict):
            continue
        href = safe_text(str(essay.get("href", "")))
        title = safe_text(str(essay.get("title", "")))
        if href and title:
            links.append(f'<li><a href="{href}">{title}</a></li>')
    if not links:
        return ""
    return '<div class="item-children"><div class="item-children-label">Essays in order</div><ol class="item-children-list">' + ''.join(links) + "</ol></div>"


def render_authority_collection_landing(doc_title: str, description: str, items: list[dict[str, str]]) -> str:
    intro = safe_text(description).strip()
    intro_html = f"<p>{intro}</p>" if intro else ""
    count_label = f"{len(items)} essays" if items else "No essays detected yet."
    toc = render_collection_sections(items)
    return (
        '<section class="pse-authority-collection">'
        + f"<h1>{safe_text(doc_title)}</h1>"
        + '<p><strong>Authority collection.</strong> Read these essays in order. This landing page keeps the collection as a table of contents rather than one bundled full-text article.</p>'
        + intro_html
        + f'<p><strong>Contents:</strong> {safe_text(count_label)}</p>'
        + toc
        + "</section>"
    )


def render_collection_navigation(collection_title: str, collection_href: str, items: list[dict[str, str]], current_slug: str, item_label: str = "Essay") -> str:
    if not items:
        return ""
    current_index = next((idx for idx, item in enumerate(items) if item.get("slug") == current_slug), -1)
    position = f"{item_label} {current_index + 1} of {len(items)}" if current_index >= 0 else ""
    links: list[str] = []
    if 0 <= current_index < len(items) - 1:
        next_item = items[current_index + 1]
        links.append('<li class="pse-discovery-item pse-discovery-item-next"><span class="pse-nav-label">Next</span><a href="' + safe_text(next_item["href"]) + '">' + safe_text(next_item["title"]) + "</a></li>")
    if current_index > 0:
        prev_item = items[current_index - 1]
        links.append('<li class="pse-discovery-item"><span class="pse-nav-label">Previous</span><a href="' + safe_text(prev_item["href"]) + '">' + safe_text(prev_item["title"]) + "</a></li>")
    links.append('<li class="pse-discovery-item"><span class="pse-nav-label">Guide</span><a href="' + safe_text(collection_href) + '">Back to ' + safe_text(collection_title) + "</a></li>")
    label = f'<p>{safe_text(position)}</p>' if position else ""
    return '<section><h2>Continue</h2>' + label + '<ul>' + ''.join(links) + "</ul></section>"
