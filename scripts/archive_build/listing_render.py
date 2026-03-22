from __future__ import annotations

import html
import re
from typing import Callable

from archive_build.collections import render_authority_entry_children, render_non_engineering_entry_children


def safe_text(value: str) -> str:
    return html.escape(value, quote=True)


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
    version_tuple = tuple(int(part) for part in version.lower()[1:].split("."))
    return ("/".join(family_parts), version, version_tuple)


def family_slug_and_version(entry: dict[str, str]) -> tuple[str, tuple[int, ...]]:
    family_key, _version, version_tuple = slug_family_info(entry["slug"])
    return family_key, version_tuple


def render_redirect_page(target_href: str, load_template: Callable[[str], str], render_template: Callable[[str, dict[str, str]], str], site_name: str) -> str:
    template = load_template("redirect.html")
    return render_template(template, {"TARGET_HREF": safe_text(target_href), "SITE_NAME": safe_text(site_name)})


def humanize_slug(slug: str) -> str:
    parts = [part for part in slug.split("-") if part]
    out: list[str] = []
    for part in parts:
        if re.fullmatch(r"v\d+(?:\.\d+)*", part, flags=re.IGNORECASE):
            out.append(part)
        else:
            out.append(part.capitalize())
    return " ".join(out) if out else slug


def render_item_card(item: dict[str, str]) -> str:
    is_pdf_only = item.get("pdf_only") == "true"
    primary_href = item.get("url") if (not is_pdf_only and item.get("url")) else item.get("pdf_url", "")
    actions: list[str] = []
    if not is_pdf_only and item.get("url"):
        actions.append(f'<a class="item-action" href="{safe_text(item["url"])}">Read</a>')
    actions.append(f'<a class="item-action" href="{safe_text(item["pdf_url"])}">PDF</a>')
    meta = " · ".join(actions)
    title_html = f'<a class="item-title-link" href="{safe_text(primary_href)}">{safe_text(item["title"])}' + "</a>" if primary_href else safe_text(item["title"])
    description = (item.get("description") or "").strip()
    essay_count = int(item.get("essay_count", "0") or "0")
    if item.get("type") == "authority" and essay_count > 0:
        suffix = f" Includes {essay_count} essays."
        if suffix not in description:
            description = (description + " " + suffix).strip() if description else suffix.strip()
    desc_html = f'<div class="item-description">{safe_text(description)}</div>' if description else ""
    children_html = ""
    if item.get("type") == "authority":
        children_html = render_authority_entry_children(item)
    elif item.get("type") == "non-engineering":
        children_html = render_non_engineering_entry_children(item)
    latest_badge = '<span class="item-badge">Latest</span>' if item.get("is_latest") == "true" else ""
    version_note = '<span class="item-version-note">Older version</span>' if item.get("is_latest") == "false" else ""
    return '<li class="archive-item">' + f'<div class="item-title">{title_html}{latest_badge}{version_note}</div>' + f"{desc_html}{children_html}<div class=\"item-actions\">{meta}</div>" + "</li>"


def render_family_block(family_label: str, latest_item: dict[str, str], all_items: list[dict[str, str]], mode: str) -> str:
    items: list[dict[str, str]] = []
    if mode == "latest":
        row = dict(latest_item)
        row["is_latest"] = "true"
        items = [row]
    else:
        for idx, item in enumerate(all_items):
            row = dict(item)
            row["is_latest"] = "true" if idx == 0 else "false"
            items.append(row)
    rendered_items = "".join(render_item_card(item) for item in items)
    heading = f"<h3>{safe_text(family_label)}</h3>" if family_label else ""
    return '<section class="group-block">' + heading + '<ul class="archive-list">' + rendered_items + "</ul></section>"


def render_sections(items: list[dict[str, str]], family_buckets: dict[tuple[str, str], list[dict[str, str]]], type_name: str, mode: str, empty_label: str) -> str:
    source_items = items if mode == "latest" else [entry for entry in items if entry["type"] == type_name]
    if not source_items:
        return f'<div class="empty-state">{safe_text(empty_label)}</div>'
    flat_items: list[dict[str, str]] = []
    family_latest: dict[str, dict[str, str]] = {}
    for item in source_items:
        family_key, version_tuple = family_slug_and_version(item)
        if family_key and version_tuple:
            family_latest[family_key] = item
        else:
            flat_items.append(item)
    blocks: list[str] = []
    if flat_items:
        rendered_items = "".join(render_item_card(dict(item, is_latest="true")) for item in sorted(flat_items, key=lambda value: value["title"].lower()))
        blocks.append('<section class="group-block"><ul class="archive-list">' + rendered_items + "</ul></section>")

    def family_order_key(family_key: str) -> tuple[int, str]:
        if mode == "latest" and type_name == "papers" and family_key.endswith("contract-authority-under-ai"):
            return (0, family_key)
        return (1, family_key)

    for family_key in sorted(family_latest, key=family_order_key):
        latest_item = family_latest[family_key]
        all_items = family_buckets.get((type_name, family_key), [latest_item])
        family_label = humanize_slug(family_key.split("/")[-1])
        blocks.append(render_family_block(family_label, latest_item, all_items, mode))
    return "\n".join(blocks)


def render_listing_page(entries: list[dict[str, str]], family_buckets: dict[tuple[str, str], list[dict[str, str]]], mode: str, content_types: list[str], site_name: str, load_template: Callable[[str], str], render_template: Callable[[str, dict[str, str]], str]) -> str:
    grouped: dict[str, list[dict[str, str]]] = {key: [] for key in content_types}
    source_entries = entries if mode == "latest" else list(entries)
    for entry in source_entries:
        if entry["type"] == "non-engineering":
            continue
        grouped[entry["type"]].append(entry)
    template = load_template("listing.html")
    title = "Latest" if mode == "latest" else "Archive"
    intro = "Current latest authority writing, papers, contracts, and replication support artifacts." if mode == "latest" else "Full archive with latest versions, older lineage, authority collection browsing, papers, contracts, and replication support artifacts."
    home_href = "../" if mode in ("latest", "archive") else "./"
    latest_href = "./" if mode == "latest" else "../latest/"
    archive_href = "./" if mode == "archive" else "../archive/"
    return render_template(template, {
        "SITE_NAME": safe_text(site_name),
        "PAGE_TITLE": safe_text(f"{title} | {site_name}"),
        "PAGE_HEADING": safe_text(title),
        "PAGE_INTRO": safe_text(intro),
        "HOME_HREF": home_href,
        "LATEST_HREF": latest_href,
        "ARCHIVE_HREF": archive_href,
        "AUTHORITY_SECTIONS": render_sections(grouped["authority"], family_buckets, "authority", mode, "No authority collections yet."),
        "PAPERS_SECTIONS": render_sections(grouped["papers"], family_buckets, "papers", mode, "No results yet."),
        "CONTRACTS_SECTIONS": render_sections(grouped["contracts"], family_buckets, "contracts", mode, "No engineering artifacts yet."),
        "REPLICATION_SECTIONS": render_sections(grouped["replication"], family_buckets, "replication", mode, "No replication materials yet."),
    })


def render_home_page(latest_entries: list[dict[str, str]], content_types: list[str], site_name: str, load_template: Callable[[str], str], render_template: Callable[[str, dict[str, str]], str]) -> str:
    grouped: dict[str, list[dict[str, str]]] = {key: [] for key in content_types}
    for entry in latest_entries:
        grouped[entry["type"]].append(entry)
    authority_count = sum(int(entry.get("essay_count", "1")) for entry in grouped["authority"])
    authority_collection_count = len(grouped["authority"])
    template = load_template("home.html")
    return render_template(template, {
        "SITE_NAME": safe_text(site_name),
        "LATEST_HREF": "./latest/",
        "ARCHIVE_HREF": "./archive/",
        "START_HREF": "./start/",
        "PROOF_HREF": "./proof/",
        "AUTHORITY_COUNT": str(authority_count),
        "AUTHORITY_COLLECTION_COUNT": str(authority_collection_count),
        "PAPERS_COUNT": str(len(grouped["papers"])),
        "CONTRACTS_COUNT": str(len(grouped["contracts"])),
        "REPLICATION_COUNT": str(len(grouped["replication"])),
    })


def find_entry_by_slug_prefix(entries: list[dict[str, str]], type_name: str, slug_prefix: str) -> dict[str, str] | None:
    for entry in entries:
        if entry.get("type") == type_name and entry.get("slug", "").startswith(slug_prefix):
            return entry
    return None


def href_or_fallback(entry: dict[str, str] | None, fallback: str) -> str:
    if entry and entry.get("url"):
        return str(entry["url"])
    return fallback


def title_or_fallback(entry: dict[str, str] | None, fallback: str) -> str:
    if entry and entry.get("title"):
        return str(entry["title"])
    return fallback


def render_start_page(latest_entries: list[dict[str, str]], site_name: str, load_template: Callable[[str], str], render_template: Callable[[str, dict[str, str]], str]) -> str:
    template = load_template("start.html")

    authority_entry = next((entry for entry in latest_entries if entry.get("type") == "authority"), None)
    non_engineering_entry = next((entry for entry in latest_entries if entry.get("type") == "non-engineering"), None)
    cce_entry = find_entry_by_slug_prefix(latest_entries, "papers", "contract-centered-engineering-")
    stability_entry = find_entry_by_slug_prefix(latest_entries, "papers", "contract-centered-iterative-stability-")
    thesis_entry = find_entry_by_slug_prefix(latest_entries, "papers", "thesis-experimental-methodology-")
    boundary_entry = find_entry_by_slug_prefix(latest_entries, "papers", "contract-authority-under-ai-")

    authority_href = href_or_fallback(authority_entry, "/latest/#authority")
    non_engineering_href = href_or_fallback(non_engineering_entry, "/non-engineering/")
    cce_href = href_or_fallback(cce_entry, "/latest/#papers")
    stability_href = href_or_fallback(stability_entry, "/latest/#papers")
    thesis_href = href_or_fallback(thesis_entry, "/latest/#replication")
    boundary_href = href_or_fallback(boundary_entry, "/latest/#papers")

    core_path_items = [
        (
            title_or_fallback(boundary_entry, "Contract Authority Under AI"),
            boundary_href,
            "States the narrower result, the surviving claim, and the authority boundary that did not hold.",
        ),
        (
            title_or_fallback(stability_entry, "Contract-Centered Iterative Stability"),
            stability_href,
            "Shows the repeated drift mechanism and the boundary where prompts stop carrying invariant scope.",
        ),
        (
            title_or_fallback(cce_entry, "Contract-Centered Engineering"),
            cce_href,
            "Explains why explicit source-of-truth artifacts still matter even when they are not the final authority surface.",
        ),
        (
            title_or_fallback(authority_entry, "Authority, Execution, and Refusal"),
            authority_href,
            "Moves from the bounded engineering result into the broader authority framing.",
        ),
    ]
    core_path_html = "".join(
        '<li><a href="{href}">{title}</a><span>{desc}</span></li>'.format(
            href=safe_text(href),
            title=safe_text(title),
            desc=safe_text(desc),
        )
        for title, href, desc in core_path_items
    )

    return render_template(template, {
        "SITE_NAME": safe_text(site_name),
        "HOME_HREF": "../",
        "LATEST_HREF": "../latest/",
        "ARCHIVE_HREF": "../archive/",
        "PROOF_HREF": "../proof/",
        "AUTHORITY_HREF": safe_text(authority_href),
        "AUTHORITY_TITLE": safe_text(title_or_fallback(authority_entry, "Authority, Execution, and Refusal")),
        "BOUNDARY_HREF": safe_text(boundary_href),
        "BOUNDARY_TITLE": safe_text(title_or_fallback(boundary_entry, "Contract Authority Under AI")),
        "NON_ENGINEERING_HREF": safe_text(non_engineering_href),
        "NON_ENGINEERING_TITLE": safe_text(title_or_fallback(non_engineering_entry, "What AI Gets Wrong When You Iterate")),
        "CCE_HREF": safe_text(cce_href),
        "CCE_TITLE": safe_text(title_or_fallback(cce_entry, "Contract-Centered Engineering")),
        "STABILITY_HREF": safe_text(stability_href),
        "STABILITY_TITLE": safe_text(title_or_fallback(stability_entry, "Contract-Centered Iterative Stability")),
        "THESIS_HREF": safe_text(thesis_href),
        "THESIS_TITLE": safe_text(title_or_fallback(thesis_entry, "Thesis & Experimental Methodology")),
        "CORE_PATH_ITEMS": core_path_html,
    })


def render_proof_page(latest_entries: list[dict[str, str]], site_name: str, load_template: Callable[[str], str], render_template: Callable[[str, dict[str, str]], str]) -> str:
    template = load_template("proof.html")

    stability_entry = find_entry_by_slug_prefix(latest_entries, "papers", "contract-centered-iterative-stability-")
    thesis_entry = find_entry_by_slug_prefix(latest_entries, "papers", "thesis-experimental-methodology-")
    replication_entry = find_entry_by_slug_prefix(latest_entries, "replication", "context-injection-research-program")
    cce_entry = find_entry_by_slug_prefix(latest_entries, "papers", "contract-centered-engineering-")
    boundary_entry = find_entry_by_slug_prefix(latest_entries, "papers", "contract-authority-under-ai-")

    return render_template(template, {
        "SITE_NAME": safe_text(site_name),
        "HOME_HREF": "../",
        "START_HREF": "../start/",
        "LATEST_HREF": "../latest/",
        "ARCHIVE_HREF": "../archive/",
        "BOUNDARY_HREF": safe_text(href_or_fallback(boundary_entry, "/latest/#papers")),
        "BOUNDARY_TITLE": safe_text(title_or_fallback(boundary_entry, "Contract Authority Under AI")),
        "STABILITY_HREF": safe_text(href_or_fallback(stability_entry, "/latest/#papers")),
        "STABILITY_TITLE": safe_text(title_or_fallback(stability_entry, "Contract-Centered Iterative Stability")),
        "THESIS_HREF": safe_text(href_or_fallback(thesis_entry, "/latest/#replication")),
        "THESIS_TITLE": safe_text(title_or_fallback(thesis_entry, "Thesis & Experimental Methodology")),
        "REPLICATION_HREF": safe_text(href_or_fallback(replication_entry, "/latest/#replication")),
        "REPLICATION_TITLE": safe_text(title_or_fallback(replication_entry, "Context Injection Research Program")),
        "CCE_HREF": safe_text(href_or_fallback(cce_entry, "/latest/#papers")),
        "CCE_TITLE": safe_text(title_or_fallback(cce_entry, "Contract-Centered Engineering")),
    })
