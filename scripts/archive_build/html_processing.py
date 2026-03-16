from __future__ import annotations

import html
import re

from bs4 import BeautifulSoup


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

    body_html = repair_flattened_nested_lists(body_html)

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

        attrs = normalize_p_attrs(match.group("attrs") or "")
        inner = match.group("body") or ""
        full = match.group(0)
        text = strip_tags_to_text(inner)
        classes_match = re.search(r'class\s*=\s*"([^"]*)"', attrs, flags=re.IGNORECASE)
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

        cleaned.append(f"<p{attrs}>{body}</p>")

    return re.sub(r"\n{3,}", "\n\n", "".join(cleaned)).strip()
