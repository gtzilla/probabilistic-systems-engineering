from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup, NavigableString, Tag


def strip_tags_to_text(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw)
    return html.unescape(re.sub(r"\s+", " ", text)).strip()


def _top_level_nodes(soup: BeautifulSoup) -> list[Tag | NavigableString]:
    return [node for node in list(soup.contents)]


def _is_block_tag(node: Tag | NavigableString) -> bool:
    return isinstance(node, Tag) and node.name in {
        "p", "div", "section", "article", "aside", "blockquote",
        "pre", "table", "ul", "ol", "hr", "h1", "h2", "h3", "h4", "h5", "h6",
    }


def _heading_level(node: Tag | NavigableString) -> int | None:
    if not isinstance(node, Tag) or not re.fullmatch(r"h[1-6]", node.name or "", flags=re.IGNORECASE):
        return None
    return int((node.name or "h0")[1:])


def _marker_value(node: Tag | NavigableString, prefix: str) -> str:
    if not isinstance(node, Tag) or node.name not in {"p", "h1", "h2", "h3", "h4", "h5", "h6"}:
        return ""
    text = strip_tags_to_text(str(node))
    match = re.match(rf"^{re.escape(prefix)}\s*(.+?)\s*$", text, flags=re.IGNORECASE)
    return match.group(1).strip() if match else ""


def _preview_text_from_nodes(nodes: list[Tag | NavigableString], max_len: int = 180) -> str:
    parts: list[str] = []
    for node in nodes:
        text = strip_tags_to_text(str(node))
        if text:
            parts.append(text)
        joined = " ".join(parts).strip()
        if len(joined) >= max_len:
            break

    preview = re.sub(r"\s+", " ", " ".join(parts)).strip()
    if len(preview) > max_len:
        return preview[: max_len - 1].rstrip() + "…"
    return preview


MONOSPACE_FONT_MARKERS = (
    "consolas",
    "roboto mono",
    "menlo",
    "monaco",
    "courier",
    "monospace",
)


def _extract_class_rule_map(exported_styles: str) -> dict[str, str]:
    rules: dict[str, str] = {}
    for class_name, declarations in re.findall(r"\.([A-Za-z0-9_-]+)\s*\{([^}]*)\}", exported_styles or "", flags=re.IGNORECASE | re.DOTALL):
        rules[class_name] = " ".join(declarations.lower().split())
    return rules


def _style_implies_code(rule: str) -> bool:
    if not rule or "font-family" not in rule:
        return False
    return any(marker in rule for marker in MONOSPACE_FONT_MARKERS)


def _style_implies_indented_block(rule: str) -> bool:
    if not rule:
        return False

    def pt_value(name: str) -> float:
        match = re.search(rf"{name}:\s*([0-9]+(?:\.[0-9]+)?)pt", rule)
        return float(match.group(1)) if match else 0.0

    margin_left = pt_value("margin-left")
    margin_right = pt_value("margin-right")
    padding_left = pt_value("padding-left")
    return margin_left >= 18 or padding_left >= 18 or (margin_left >= 12 and margin_right >= 12)


def _extract_code_text(node: Tag) -> str:
    parts: list[str] = []
    for descendant in node.descendants:
        if isinstance(descendant, NavigableString):
            parts.append(str(descendant))
        elif isinstance(descendant, Tag) and descendant.name == "br":
            parts.append("\n")

    text = html.unescape("".join(parts)).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+$", "", line) for line in text.splitlines()]
    normalized = "\n".join(lines).strip("\n")
    return re.sub(r"\n{3,}", "\n\n", normalized)


def convert_google_docs_code_tables(body_html: str, exported_styles: str) -> str:
    class_rules = _extract_class_rule_map(exported_styles)
    monospace_classes = {name for name, rule in class_rules.items() if _style_implies_code(rule)}
    if not monospace_classes:
        return body_html

    soup = BeautifulSoup(body_html, "html.parser")
    for table in soup.find_all("table"):
        rows = table.find_all("tr", recursive=True)
        cells = table.find_all(["td", "th"], recursive=True)
        if len(rows) != 1 or len(cells) != 1:
            continue

        cell = cells[0]
        descendant_classes: set[str] = set()
        for tag in cell.find_all(True):
            descendant_classes.update(tag.get("class", []))
        if not (descendant_classes & monospace_classes):
            continue

        code_text = _extract_code_text(cell)
        if len(code_text.strip()) < 12:
            continue

        pre = soup.new_tag("pre", attrs={"class": "pse-code-block"})
        code = soup.new_tag("code")
        code.string = code_text
        pre.append(code)
        table.replace_with(pre)

    return "".join(str(node) for node in soup.contents)


def wrap_tables_for_scroll(body_html: str) -> str:
    soup = BeautifulSoup(body_html, "html.parser")
    for table in soup.find_all("table"):
        parent = table.parent
        if isinstance(parent, Tag) and parent.name == "div" and "pse-table-wrap" in (parent.get("class") or []):
            continue
        wrapper = soup.new_tag("div", attrs={"class": "pse-table-wrap"})
        table.wrap(wrapper)
    return "".join(str(node) for node in soup.contents)


def apply_collapsible_markers(body_html: str) -> str:
    soup = BeautifulSoup(body_html, "html.parser")
    nodes = _top_level_nodes(soup)
    idx = 0

    while idx < len(nodes):
        marker_node = nodes[idx]
        title = _marker_value(marker_node, "Collapsed:")
        if not title:
            idx += 1
            continue

        marker_level = _heading_level(marker_node)
        summary_text = ""
        summary_node: Tag | NavigableString | None = None
        content_start = idx + 1

        while content_start < len(nodes):
            candidate = nodes[content_start]
            if isinstance(candidate, NavigableString) and not candidate.strip():
                content_start += 1
                continue
            break

        if content_start < len(nodes):
            candidate = nodes[content_start]
            summary_value = _marker_value(candidate, "Summary:")
            if summary_value:
                summary_text = summary_value
                summary_node = candidate
                content_start += 1

        content_end = content_start
        captured_nodes: list[Tag | NavigableString] = []

        while content_end < len(nodes):
            candidate = nodes[content_end]
            level = _heading_level(candidate)
            if level is not None:
                if marker_level is not None and level <= marker_level:
                    break
                if marker_level is None:
                    break
            captured_nodes.append(candidate)
            content_end += 1

        block_nodes = [node for node in captured_nodes if not (isinstance(node, NavigableString) and not node.strip())]
        has_block_content = any(_is_block_tag(node) or (isinstance(node, NavigableString) and node.strip()) for node in block_nodes)
        if not has_block_content:
            idx += 1
            continue

        contains_dense_block = any(isinstance(node, Tag) and node.name in {"pre", "table"} for node in block_nodes)
        preview_text = summary_text or ("Expand for full excerpt." if contains_dense_block else _preview_text_from_nodes(block_nodes))

        feature = soup.new_tag("section", attrs={"class": "pse-feature-block"})
        header = soup.new_tag("div", attrs={"class": "pse-feature-block-header"})

        title_el = soup.new_tag("h3", attrs={"class": "pse-feature-block-title"})
        title_el.string = title
        header.append(title_el)

        if preview_text:
            summary_el = soup.new_tag("p", attrs={"class": "pse-feature-block-summary"})
            summary_el.string = preview_text
            header.append(summary_el)

        body = soup.new_tag("div", attrs={"class": "pse-feature-block-body"})
        for node in block_nodes:
            body.append(node.extract())

        feature.append(header)
        feature.append(body)

        marker_node.insert_before(feature)
        marker_node.extract()
        if summary_node is not None:
            summary_node.extract()

        nodes = _top_level_nodes(soup)
        try:
            idx = nodes.index(feature) + 1
        except ValueError:
            idx = content_end

    return "".join(str(node) for node in soup.contents)


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


def _extract_list_signature(tag) -> tuple[str, int] | None:
    classes = tag.get("class", []) if hasattr(tag, "get") else []
    for cls in classes:
        match = re.fullmatch(r"(lst-kix_[A-Za-z0-9]+)-(\d+)", cls)
        if match:
            return match.group(1), int(match.group(2))
    return None


def repair_flattened_nested_lists(body_html: str) -> str:
    """
    Google Docs exports some nested lists as sibling <ul>/<ol> blocks instead of
    nesting the child list inside the preceding parent <li>. Repair that shape
    when the list family and level classes make the relationship deterministic.
    """
    soup = BeautifulSoup(body_html, "html.parser")

    changed = True
    while changed:
        changed = False
        for list_tag in soup.find_all(["ul", "ol"]):
            signature = _extract_list_signature(list_tag)
            if not signature:
                continue

            sibling = list_tag.next_sibling
            while sibling is not None and (
                (isinstance(sibling, str) and not sibling.strip())
                or getattr(sibling, "name", None) is None
            ):
                sibling = sibling.next_sibling

            if getattr(sibling, "name", None) not in {"ul", "ol"}:
                continue

            sibling_signature = _extract_list_signature(sibling)
            if not sibling_signature:
                continue

            if sibling_signature[0] != signature[0] or sibling_signature[1] != signature[1] + 1:
                continue

            last_li = next(reversed(list_tag.find_all("li", recursive=False)), None)
            if last_li is None:
                continue

            last_li.append("\n")
            last_li.append(sibling.extract())
            changed = True

    return "".join(str(node) for node in soup.contents)


def refine_body_html(body_html: str, exported_styles: str = "") -> str:
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

    class_rules = _extract_class_rule_map(exported_styles)
    indented_block_classes = {name for name, rule in class_rules.items() if _style_implies_indented_block(rule)}

    body_html = repair_flattened_nested_lists(body_html)
    body_html = convert_google_docs_code_tables(body_html, exported_styles)
    body_html = wrap_tables_for_scroll(body_html)
    body_html = apply_collapsible_markers(body_html)

    def has_structural_content(raw: str) -> bool:
        return bool(re.search(r"<(img|svg|table|hr)\b", raw, flags=re.IGNORECASE))

    def is_empty_paragraph(inner_html: str) -> bool:
        if has_structural_content(inner_html):
            return False
        text = strip_tags_to_text(inner_html)
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

        original_attrs = match.group("attrs") or ""
        attrs = normalize_p_attrs(original_attrs)
        inner = match.group("body") or ""
        full = match.group(0)
        text = strip_tags_to_text(inner)
        classes_match = re.search(r'class\s*=\s*"([^"]*)"', original_attrs, flags=re.IGNORECASE)
        class_list = (classes_match.group(1).split() if classes_match else [])

        pieces.append(
            {
                "kind": "paragraph",
                "html": full,
                "attrs": attrs,
                "body": inner,
                "text": text,
                "empty": is_empty_paragraph(inner),
                "classes": class_list,
            }
        )
        last_end = match.end()

    if last_end < len(body_html):
        pieces.append({"kind": "raw", "html": body_html[last_end:]})

    title_classes = {"title", "subtitle"}
    skip_until = -1
    cleaned: list[str] = []

    for idx, piece in enumerate(pieces):
        if idx <= skip_until:
            continue

        if piece.get("kind") != "paragraph":
            cleaned.append(str(piece["html"]))
            continue

        classes = set(piece.get("classes", []))
        attrs = str(piece.get("attrs", ""))
        text = str(piece.get("text", ""))
        empty = bool(piece.get("empty", False))
        body = str(piece.get("body", ""))

        if empty:
            continue

        if title_classes & classes and text:
            group_indexes = [idx]
            j = idx + 1
            while j < len(pieces):
                nxt = pieces[j]
                if nxt.get("kind") != "paragraph":
                    break
                nxt_classes = set(nxt.get("classes", []))
                nxt_text = str(nxt.get("text", ""))
                if title_classes & nxt_classes and nxt_text == text:
                    group_indexes.append(j)
                    j += 1
                    continue
                break

            skip_until = group_indexes[-1]
            cleaned.append(f'<h1 class="pse-title">{html.escape(text)}</h1>')
            continue

        if indented_block_classes and classes & indented_block_classes and text:
            cleaned.append(f'<blockquote class="pse-blockquote"><p{attrs}>{body}</p></blockquote>')
            continue

        cleaned.append(f"<p{attrs}>{body}</p>")

    return re.sub(r"\n{3,}", "\n\n", "".join(cleaned)).strip()
