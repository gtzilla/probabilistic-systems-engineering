from __future__ import annotations

import re

from archive_build.html_processing import strip_tags_to_text

NON_ENGINEERING_READING_LINKS = [
    ("Start here: Authority, Execution, and Refusal", "/authority/authority-execution-refusal/"),
    ("The proof: Contract-Centered Iterative Stability", "/papers/contract-centered-iterative-stability-v4.7.3/"),
    ("The method: Contract-Centered Engineering", "/papers/contract-centered-engineering-v2.17/"),
    ("The mechanism: Breaking the Loop", "/papers/breaking-the-loop-v1.0/"),
    ("Replication materials", "/replication/context-injection-research-program/"),
]


def infer_non_engineering_theme(metadata: dict[str, object], doc_title: str = '') -> str:
    slug = str(metadata.get('slug', '')).lower()
    title = str(doc_title or metadata.get('title', '')).lower()
    combined = f'{slug} {title}'
    if 'design' in combined:
        return 'design'
    if 'startup' in combined or 'growth' in combined:
        return 'startup'
    if 'enterprise' in combined or 'public-company' in combined or 'board' in combined or 'risk committee' in combined:
        return 'enterprise'
    if 'research behind this' in combined or 'proof' in combined or 'replication' in combined:
        return 'research'
    return 'default'


def enhance_non_engineering_body_html(body_html: str) -> str:
    def clean_class_attrs(raw: str) -> str:
        def repl(match: re.Match[str]) -> str:
            quote = match.group(1)
            classes = [c for c in match.group(2).split() if not re.fullmatch(r'c\d+', c)]
            return '' if not classes else f' class={quote}{" ".join(classes)}{quote}'

        raw = re.sub(r'\sclass=(["\'])(.*?)\1', repl, raw, flags=re.IGNORECASE)
        raw = re.sub(r'\s{2,}', ' ', raw)
        return raw

    def strip_attrs_for_tag(tag_name: str, html_text: str, *, drop_style: bool = True, drop_all_classes: bool = False) -> str:
        pattern = re.compile(rf'<{tag_name}([^>]*)>', flags=re.IGNORECASE)

        def repl(match: re.Match[str]) -> str:
            attrs = match.group(1) or ''
            if drop_style:
                attrs = re.sub(r'\sstyle=("[^"]*"|\'[^\']*\')', '', attrs, flags=re.IGNORECASE)
            if drop_all_classes:
                attrs = re.sub(r'\sclass=("[^"]*"|\'[^\']*\')', '', attrs, flags=re.IGNORECASE)
            else:
                attrs = clean_class_attrs(attrs)
            attrs = re.sub(r'\s{2,}', ' ', attrs).rstrip()
            return f'<{tag_name}{attrs}>'

        return pattern.sub(repl, html_text)

    def add_class(match: re.Match[str], class_name: str) -> str:
        attrs = match.group(1) or ""
        inner = match.group(2)
        if 'class=' in attrs:
            attrs = re.sub(r'class="([^"]*)"', lambda m: f'class="{m.group(1)} {class_name}"', attrs, count=1)
            attrs = re.sub(r"class='([^']*)'", lambda m: f"class='{m.group(1)} {class_name}'", attrs, count=1)
        else:
            attrs = f'{attrs} class="{class_name}"'
        return f'<p{attrs}>{inner}</p>'

    def classify_paragraph(match: re.Match[str]) -> str:
        text = strip_tags_to_text(match.group(2)).strip()
        normalized = re.sub(r'\s+', ' ', text)
        if normalized == 'AI binds to the scope you name.':
            return add_class(match, 'pse-hero-quote')
        if normalized.startswith('Result:'):
            return add_class(match, 'pse-result')
        if len(normalized) <= 72 and normalized and normalized[0].isupper() and not normalized.endswith(('.', '?', '!', ':')) and 1 <= normalized.count(' ') <= 7:
            return add_class(match, 'pse-scenario-label')
        if normalized == 'The shortest version is this:':
            return add_class(match, 'pse-kicker')
        return match.group(0)

    for tag_name in ('h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'table', 'thead', 'tbody', 'tr', 'th', 'td', 'p', 'li', 'strong', 'b', 'em', 'i', 'a'):
        body_html = strip_attrs_for_tag(tag_name, body_html)
    body_html = re.sub(r'</?span\b[^>]*>', '', body_html, flags=re.IGNORECASE)
    body_html = re.sub(r'<p([^>]*)>(.*?)</p>', classify_paragraph, body_html, flags=re.DOTALL)
    body_html = body_html.replace('<table', '<div class="pse-table-wrap"><table', 1).replace('</table>', '</table></div>', 1)
    for label, href in NON_ENGINEERING_READING_LINKS:
        body_html = re.sub(
            rf'(<p[^>]*>\s*(?:<strong>)?){re.escape(label)}((?:<br\s*/?>)(?:</strong>)?)',
            rf'\1<a href="{href}">{label}</a>\2',
            body_html,
            flags=re.IGNORECASE,
        )
    return body_html
