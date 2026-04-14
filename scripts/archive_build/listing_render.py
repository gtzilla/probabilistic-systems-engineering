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



def entry_sort_key(entry: dict[str, str]) -> tuple[int, str, str]:
    publication_date = str(entry.get("publication_date", "") or "")
    title = str(entry.get("title", "")).lower()
    return (1 if publication_date else 0, publication_date, title)


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
    if item.get("pdf_url"):
        actions.append(f'<a class="item-action" href="{safe_text(item["pdf_url"])}">PDF</a>')
    meta = " · ".join(actions)
    title_html = (
        f'<a class="item-title-link" href="{safe_text(primary_href)}">{safe_text(item["title"])}' + "</a>"
        if primary_href else safe_text(item["title"])
    )
    description = (item.get("description") or "").strip()
    essay_count = int(item.get("essay_count", "0") or "0")
    if item.get("type") == "authority" and essay_count > 0:
        suffix = f" Includes {essay_count} essays."
        if suffix not in description:
            description = (description + " " + suffix).strip() if description else suffix.strip()
    date_html = ""
    if item.get("archive_date"):
        date_html = f'<div class="item-date">{safe_text(item["archive_date"])}' + "</div>"
    desc_html = f'<div class="item-description">{safe_text(description)}</div>' if description else ""
    children_html = ""
    if item.get("type") == "authority":
        children_html = render_authority_entry_children(item)
    elif item.get("type") == "non-engineering":
        children_html = render_non_engineering_entry_children(item)
    latest_badge = '<span class="item-badge">Latest</span>' if item.get("is_latest") == "true" else ""
    version_note = '<span class="item-version-note">Older version</span>' if item.get("is_latest") == "false" else ""
    return (
        '<li class="archive-item">'
        + f'<div class="item-title">{title_html}{latest_badge}{version_note}</div>'
        + f'{date_html}{desc_html}{children_html}'
        + (f'<div class="item-actions">{meta}</div>' if meta else '')
        + '</li>'
    )


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

    if mode == "latest" and type_name == "papers":
        paper_blocks: list[tuple[tuple[str, str], str]] = []
        for item in flat_items:
            rendered_items = render_item_card(dict(item, is_latest="true"))
            block_html = '<section class="group-block"><ul class="archive-list">' + rendered_items + '</ul></section>'
            paper_blocks.append((entry_sort_key(item), block_html))
        for family_key, latest_item in family_latest.items():
            all_items = family_buckets.get((type_name, family_key), [latest_item])
            family_label = humanize_slug(family_key.split("/")[-1])
            block_html = render_family_block(family_label, latest_item, all_items, mode)
            paper_blocks.append((entry_sort_key(latest_item), block_html))
        if not paper_blocks:
            return f'<div class="empty-state">{safe_text(empty_label)}</div>'
        paper_blocks.sort(key=lambda row: row[0], reverse=True)
        return "\n".join(block_html for _sort_key, block_html in paper_blocks)

    blocks: list[str] = []
    if flat_items:
        flat_sorted = sorted(flat_items, key=entry_sort_key, reverse=True) if type_name == "papers" else sorted(flat_items, key=lambda value: value["title"].lower())
        rendered_items = "".join(render_item_card(dict(item, is_latest="true")) for item in flat_sorted)
        blocks.append('<section class="group-block"><ul class="archive-list">' + rendered_items + "</ul></section>")

    def family_order_key(family_key: str) -> tuple[str, str]:
        latest_item = family_latest[family_key]
        if type_name == "papers":
            return (latest_item.get("publication_date", ""), family_key)
        return ("", family_key)

    for family_key in sorted(family_latest.keys(), key=family_order_key, reverse=(type_name == "papers")):
        latest_item = family_latest[family_key]
        all_items = family_buckets.get((type_name, family_key), [latest_item])
        family_label = humanize_slug(family_key.split("/")[-1])
        blocks.append(render_family_block(family_label, latest_item, all_items, mode))
    return "\n".join(blocks)

def render_listing_page(entries: list[dict[str, str]], family_buckets: dict[tuple[str, str], list[dict[str, str]]], mode: str, content_types: list[str], site_name: str, site_url: str, og_image_url: str, og_image_alt: str, favicon_ico_href: str, favicon_32_href: str, favicon_16_href: str, apple_touch_icon_href: str, load_template: Callable[[str], str], render_template: Callable[[str, dict[str, str]], str]) -> str:
    grouped: dict[str, list[dict[str, str]]] = {key: [] for key in content_types}
    source_entries = entries if mode == "latest" else list(entries)
    for entry in source_entries:
        if entry["type"] == "non-engineering":
            continue
        grouped[entry["type"]].append(entry)
    template = load_template("listing.html")
    title = "Latest" if mode == "latest" else "Archive"
    intro = "Current papers and supporting protocols & contracts." if mode == "latest" else "Full archive with current work, older lineage, protocols & contracts, authority essays, and replication materials."
    home_href = "../" if mode in ("latest", "archive") else "./"
    latest_href = "./" if mode == "latest" else "../latest/"
    archive_href = "./" if mode == "archive" else "../archive/"
    canonical_url = f"{site_url}/{mode}/"
    return render_template(template, {
        "SITE_NAME": safe_text(site_name),
        "PAGE_TITLE": safe_text(f"{title} | {site_name}"),
        "PAGE_DESCRIPTION": safe_text(intro),
        "CANONICAL_URL": safe_text(canonical_url),
        "OG_IMAGE_URL": safe_text(og_image_url),
        "OG_IMAGE_ALT": safe_text(og_image_alt),
        "FAVICON_ICO_HREF": safe_text(favicon_ico_href),
        "FAVICON_32_HREF": safe_text(favicon_32_href),
        "FAVICON_16_HREF": safe_text(favicon_16_href),
        "APPLE_TOUCH_ICON_HREF": safe_text(apple_touch_icon_href),
        "PAGE_HEADING": safe_text(title),
        "PAGE_INTRO": safe_text(intro),
        "HOME_HREF": home_href,
        "LATEST_HREF": latest_href,
        "ARCHIVE_HREF": archive_href,
        "ABOUT_HREF": "../about/" if mode in ("latest", "archive") else "./about/",
        "RESEARCH_HREF": "../research/" if mode in ("latest", "archive") else "./research/",
        "PAPERS_SECTIONS": render_sections(grouped["papers"], family_buckets, "papers", mode, "No results yet."),
        "CONTRACTS_SECTIONS": render_sections(grouped["contracts"], family_buckets, "contracts", mode, "No engineering artifacts yet."),
        "REPLICATION_SECTION_HTML": "" if mode == "latest" else '<section id="replication" class="archive-section archive-section-replication"><h2>Replication &amp; verification</h2><p class="section-note">Portable rerun support, comparison packets, and verification materials. Useful for repeatability and auditability, but secondary to the primary reading path.</p>' + render_sections(grouped["replication"], family_buckets, "replication", mode, "No replication materials yet.") + "</section>",
        "AUTHORITY_SECTION_HTML": "" if mode == "latest" else '<section id="authority" class="archive-section archive-section-authority"><h2>Authority</h2><p class="section-note">Linked essays and collections on where control actually lives and why understanding alone does not restore it.</p>' + render_sections(grouped["authority"], family_buckets, "authority", mode, "No authority collections yet.") + "</section>",
    })


def render_home_page(latest_entries: list[dict[str, str]], content_types: list[str], site_name: str, site_url: str, og_image_url: str, og_image_alt: str, favicon_ico_href: str, favicon_32_href: str, favicon_16_href: str, apple_touch_icon_href: str, load_template: Callable[[str], str], render_template: Callable[[str, dict[str, str]], str]) -> str:
    grouped: dict[str, list[dict[str, str]]] = {key: [] for key in content_types}
    for entry in latest_entries:
        grouped[entry["type"]].append(entry)

    template = load_template("home.html")
    page_description = "An evolving research corpus on AI-assisted software work: omitted scope, blended inference, default fill-in, VDG, preserved truth, and where authority actually does and does not live."

    boundary_entry = find_entry_by_slug_prefix(latest_entries, "papers", "contract-authority-under-ai-")
    vdg_entry = find_entry_by_slug_prefix(latest_entries, "papers", "why-verified-deduction-gap-")

    newest_papers = sorted(grouped["papers"], key=entry_sort_key, reverse=True)
    dynamic_papers = [
        entry
        for entry in newest_papers
        if entry.get("slug") != (boundary_entry or {}).get("slug")
    ][:2]

    current_cards: list[str] = []
    for entry in dynamic_papers:
        current_cards.append(
            render_home_card(
                title_or_fallback(entry, "Untitled paper"),
                href_or_fallback(entry, "./latest/"),
                str(entry.get("description") or "Current paper from the live research thread."),
            )
        )
    if boundary_entry:
        current_cards.append(
            render_home_card(
                title_or_fallback(boundary_entry, "Contract Authority Under AI"),
                href_or_fallback(boundary_entry, "./latest/"),
                "The strongest contract-authority claim, the research boundary, and the narrower result that survived.",
                "current-boundary",
            )
        )
    if vdg_entry is None:
        vdg_entry = dynamic_papers[0] if dynamic_papers else boundary_entry

    protocol_links_html = "".join(
        render_protocol_link(str(entry.get("title", "Untitled artifact")), str(entry.get("url") or entry.get("pdf_url") or "./latest/#contracts"))
        for entry in grouped["contracts"]
    )

    return render_template(template, {
        "SITE_NAME": safe_text(site_name),
        "PAGE_TITLE": safe_text(site_name),
        "PAGE_DESCRIPTION": safe_text(page_description),
        "CANONICAL_URL": safe_text(f"{site_url}/"),
        "OG_IMAGE_URL": safe_text(og_image_url),
        "OG_IMAGE_ALT": safe_text(og_image_alt),
        "FAVICON_ICO_HREF": safe_text(favicon_ico_href),
        "FAVICON_32_HREF": safe_text(favicon_32_href),
        "FAVICON_16_HREF": safe_text(favicon_16_href),
        "APPLE_TOUCH_ICON_HREF": safe_text(apple_touch_icon_href),
        "LATEST_HREF": "./latest/",
        "ARCHIVE_HREF": "./archive/",
        "ABOUT_HREF": "./about/",
        "RESEARCH_HREF": "./research/",
        "VDG_HREF": safe_text(href_or_fallback(vdg_entry, "./latest/")),
        "CURRENT_THREAD_CARDS": "".join(current_cards),
        "PROTOCOLS_AND_CONTRACTS_LINKS": protocol_links_html,
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

def render_home_card(title: str, href: str, description: str, card_class: str = "current-live") -> str:
    return (
        '<a class="current-card ' + safe_text(card_class) + '" href="' + safe_text(href) + '">'
        + '<span class="eyebrow">Paper</span>'
        + '<h3>' + safe_text(title) + '</h3>'
        + '<p>' + safe_text(description) + '</p>'
        + '</a>'
    )


def render_protocol_link(title: str, href: str) -> str:
    return (
        '<a class="protocol-link" href="' + safe_text(href) + '">'
        + '<span class="eyebrow">Artifact</span>'
        + '<h3>' + safe_text(title) + '</h3>'
        + '</a>'
    )



def render_info_page(page_slug: str, page_title: str, page_description: str, page_kicker: str, body_html: str, site_name: str, site_url: str, og_image_url: str, og_image_alt: str, favicon_ico_href: str, favicon_32_href: str, favicon_16_href: str, apple_touch_icon_href: str, load_template: Callable[[str], str], render_template: Callable[[str, dict[str, str]], str]) -> str:
    template = load_template("info_page.html")
    return render_template(template, {
        "SITE_NAME": safe_text(site_name),
        "PAGE_TITLE": safe_text(f"{page_title} | {site_name}"),
        "PAGE_DESCRIPTION": safe_text(page_description),
        "CANONICAL_URL": safe_text(f"{site_url}/{page_slug}/"),
        "OG_IMAGE_URL": safe_text(og_image_url),
        "OG_IMAGE_ALT": safe_text(og_image_alt),
        "FAVICON_ICO_HREF": safe_text(favicon_ico_href),
        "FAVICON_32_HREF": safe_text(favicon_32_href),
        "FAVICON_16_HREF": safe_text(favicon_16_href),
        "APPLE_TOUCH_ICON_HREF": safe_text(apple_touch_icon_href),
        "PAGE_KICKER": safe_text(page_kicker),
        "PAGE_HEADING": safe_text(page_title),
        "PAGE_BODY_HTML": body_html,
        "HOME_HREF": "../",
        "LATEST_HREF": "../latest/",
        "ARCHIVE_HREF": "../archive/",
        "ABOUT_HREF": "../about/",
        "RESEARCH_HREF": "../research/",
    })


def render_about_page(site_name: str, site_url: str, og_image_url: str, og_image_alt: str, favicon_ico_href: str, favicon_32_href: str, favicon_16_href: str, apple_touch_icon_href: str, load_template: Callable[[str], str], render_template: Callable[[str, dict[str, str]], str]) -> str:
    body_html = (
        '<p>Gregory Tomlinson is a software engineer and writer.</p>'
        "<p>I&apos;ve spent years working in software, and a lot of my writing grows out of that practice.</p>"
        "<p>I&apos;ve been working in software long enough that this moment in AI feels, to me, a lot like the early Web2.0 era: noisy, fast-moving, and full of real new possibilities.</p>"
        '<p>I write to think, test ideas, and make the underlying mechanisms more visible.</p>'
        '<div class="contact-block">'
        '<h2>Elsewhere</h2>'
        '<ul class="contact-list">'
        '<li><button type="button" class="email-reveal-button" data-email-reveal data-local="gregory.tomlinson" data-domain="gmail.com">Reveal email</button><span class="email-reveal-output" data-email-output aria-live="polite"></span></li>'
        '<li><a href="https://github.com/gtzilla">GitHub</a></li>'
        '<li><a href="https://www.linkedin.com/in/gregorytomlinson/">LinkedIn</a></li>'
        '</ul>'
        '</div>'
        '<script>'
        '(function(){'
        'var button=document.querySelector("[data-email-reveal]");'
        'var output=document.querySelector("[data-email-output]");'
        'if(!button||!output){return;}'
        'button.addEventListener("click",function(){'
        'var local=button.getAttribute("data-local")||"";'
        'var domain=button.getAttribute("data-domain")||"";'
        'if(!local||!domain){return;}'
        'var email=local+"@"+domain;'
        'var link=document.createElement("a");'
        'link.href="mailto:"+email;'
        'link.textContent=email;'
        'output.textContent=" ";'
        'output.appendChild(link);'
        'button.disabled=true;'
        'button.textContent="Email";'
        '});'
        '})();'
        '</script>'
    )
    return render_info_page(
        "about",
        "About",
        "About Gregory Tomlinson.",
        "About",
        body_html,
        site_name,
        site_url,
        og_image_url,
        og_image_alt,
        favicon_ico_href,
        favicon_32_href,
        favicon_16_href,
        apple_touch_icon_href,
        load_template,
        render_template,
    )


def render_research_page(site_name: str, site_url: str, og_image_url: str, og_image_alt: str, favicon_ico_href: str, favicon_32_href: str, favicon_16_href: str, apple_touch_icon_href: str, load_template: Callable[[str], str], render_template: Callable[[str, dict[str, str]], str]) -> str:
    body_html = (
        '<p>This site is an evolving research corpus on AI-assisted software development.</p>'
        '<p>It studies what breaks in one response or across change, what support artifacts help preserve truth, and where authority does and does not live when software work is mediated by AI.</p>'
        '<p>The corpus includes papers, experiments, protocols and contracts, and archived lineage from earlier phases of the work.</p>'
        '<p>Earlier phases tested stronger contract-centered claims. Some of those claims did not hold. The work continued by narrowing, revising, and following what survived.</p>'
        '<p>Current threads include VDG, omitted scope, blended inference, default fill-in, review burden, preserved truth, and refusal surfaces.</p>'
    )
    return render_info_page(
        "research",
        "AI-Assisted Software Development Research",
        "Research framing for the AI-assisted software development corpus.",
        "Research",
        body_html,
        site_name,
        site_url,
        og_image_url,
        og_image_alt,
        favicon_ico_href,
        favicon_32_href,
        favicon_16_href,
        apple_touch_icon_href,
        load_template,
        render_template,
    )

def render_start_page(latest_entries: list[dict[str, str]], site_name: str, site_url: str, og_image_url: str, og_image_alt: str, favicon_ico_href: str, favicon_32_href: str, favicon_16_href: str, apple_touch_icon_href: str, load_template: Callable[[str], str], render_template: Callable[[str, dict[str, str]], str]) -> str:
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
    thesis_href = href_or_fallback(thesis_entry, "/archive/#replication")
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
        (
            '<li>'
            '<a class="reading-path-link" href="{href}">{title}</a>'
            '<p class="reading-path-desc">{desc}</p>'
            '</li>'
        ).format(
            href=safe_text(href),
            title=safe_text(title),
            desc=safe_text(desc),
        )
        for title, href, desc in core_path_items
    )

    return render_template(template, {
        "SITE_NAME": safe_text(site_name),
        "PAGE_DESCRIPTION": safe_text("Start with the bounded result, then move into iterative stability, the broader engineering frame, and the authority essays."),
        "CANONICAL_URL": safe_text(f"{site_url}/start/"),
        "OG_IMAGE_URL": safe_text(og_image_url),
        "OG_IMAGE_ALT": safe_text(og_image_alt),
        "FAVICON_ICO_HREF": safe_text(favicon_ico_href),
        "FAVICON_32_HREF": safe_text(favicon_32_href),
        "FAVICON_16_HREF": safe_text(favicon_16_href),
        "APPLE_TOUCH_ICON_HREF": safe_text(apple_touch_icon_href),
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


def render_proof_page(latest_entries: list[dict[str, str]], site_name: str, site_url: str, og_image_url: str, og_image_alt: str, favicon_ico_href: str, favicon_32_href: str, favicon_16_href: str, apple_touch_icon_href: str, load_template: Callable[[str], str], render_template: Callable[[str, dict[str, str]], str]) -> str:
    template = load_template("proof.html")

    stability_entry = find_entry_by_slug_prefix(latest_entries, "papers", "contract-centered-iterative-stability-")
    thesis_entry = find_entry_by_slug_prefix(latest_entries, "papers", "thesis-experimental-methodology-")
    replication_entry = find_entry_by_slug_prefix(latest_entries, "replication", "context-injection-research-program")
    cce_entry = find_entry_by_slug_prefix(latest_entries, "papers", "contract-centered-engineering-")
    boundary_entry = find_entry_by_slug_prefix(latest_entries, "papers", "contract-authority-under-ai-")

    return render_template(template, {
        "SITE_NAME": safe_text(site_name),
        "PAGE_DESCRIPTION": safe_text("A bounded proof path: what is supported, what was tested, and where the current claims stop."),
        "CANONICAL_URL": safe_text(f"{site_url}/proof/"),
        "OG_IMAGE_URL": safe_text(og_image_url),
        "OG_IMAGE_ALT": safe_text(og_image_alt),
        "FAVICON_ICO_HREF": safe_text(favicon_ico_href),
        "FAVICON_32_HREF": safe_text(favicon_32_href),
        "FAVICON_16_HREF": safe_text(favicon_16_href),
        "APPLE_TOUCH_ICON_HREF": safe_text(apple_touch_icon_href),
        "HOME_HREF": "../",
        "START_HREF": "../start/",
        "LATEST_HREF": "../latest/",
        "ARCHIVE_HREF": "../archive/",
        "BOUNDARY_HREF": safe_text(href_or_fallback(boundary_entry, "/latest/#papers")),
        "BOUNDARY_TITLE": safe_text(title_or_fallback(boundary_entry, "Contract Authority Under AI")),
        "STABILITY_HREF": safe_text(href_or_fallback(stability_entry, "/latest/#papers")),
        "STABILITY_TITLE": safe_text(title_or_fallback(stability_entry, "Contract-Centered Iterative Stability")),
        "THESIS_HREF": safe_text(href_or_fallback(thesis_entry, "/archive/#replication")),
        "THESIS_TITLE": safe_text(title_or_fallback(thesis_entry, "Thesis & Experimental Methodology")),
        "REPLICATION_HREF": safe_text(href_or_fallback(replication_entry, "/archive/#replication")),
        "REPLICATION_TITLE": safe_text(title_or_fallback(replication_entry, "Context Injection Research Program")),
        "CCE_HREF": safe_text(href_or_fallback(cce_entry, "/latest/#papers")),
        "CCE_TITLE": safe_text(title_or_fallback(cce_entry, "Contract-Centered Engineering")),
    })
