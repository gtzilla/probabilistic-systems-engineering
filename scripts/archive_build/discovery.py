from __future__ import annotations

import html
import json
import math
import os
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


def normalize_for_match(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"[^a-z0-9]+", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def significant_tokens(text: str) -> list[str]:
    stopwords = {
        "the", "and", "for", "with", "from", "that", "this", "into", "under", "when",
        "what", "why", "how", "your", "their", "about", "then", "than", "over", "does",
        "have", "has", "had", "are", "was", "were", "will", "its", "it", "not", "but",
        "can", "you", "they", "our", "his", "her", "she", "him", "them", "because",
    }
    return [
        token for token in normalize_for_match(text).split()
        if len(token) > 2 and token not in stopwords
    ]


def unique_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def slug_reference_phrases(slug: str) -> list[str]:
    leaf = slug.split("/")[-1]
    parts = [part for part in leaf.split("-") if part]
    phrases = [" ".join(parts)] if parts else []
    if len(parts) >= 3:
        phrases.append(" ".join(parts[:3]))
    if len(parts) >= 4:
        phrases.append(" ".join(parts[:4]))
    return unique_preserve_order([p.strip() for p in phrases if len(p.strip()) >= 12])


def recommendation_source_text(metadata: dict[str, object], full_text: str) -> str:
    parts = [str(metadata.get("title", "")), str(metadata.get("description", "")), full_text]
    return "\n".join(part for part in parts if part).strip()


def document_match_context(metadata: dict[str, object], full_text: str) -> dict[str, object]:
    title = str(metadata.get("title", ""))
    description = str(metadata.get("description", ""))
    source_text = recommendation_source_text(metadata, full_text)
    norm_text = normalize_for_match(source_text)
    return {
        "slug": str(metadata["slug"]),
        "content_type": str(metadata.get("content_type", "")),
        "kind": str(metadata.get("kind", "")),
        "title": title,
        "title_phrase": normalize_for_match(title),
        "title_tokens": significant_tokens(title),
        "slug_phrases": slug_reference_phrases(str(metadata.get("slug", ""))),
        "version": normalize_for_match(str(metadata.get("version", ""))),
        "norm_text": norm_text,
        "description": description,
        "source_text": source_text,
    }


def compute_tfidf_vectors(contexts: dict[str, dict[str, object]]) -> dict[str, dict[str, float]]:
    documents: dict[str, Counter[str]] = {}
    document_frequency: Counter[str] = Counter()

    for slug, ctx in contexts.items():
        tokens = significant_tokens(str(ctx["source_text"]))
        counts = Counter(tokens)
        documents[slug] = counts
        for token in counts:
            document_frequency[token] += 1

    total_docs = max(1, len(documents))
    vectors: dict[str, dict[str, float]] = {}
    for slug, counts in documents.items():
        if not counts:
            vectors[slug] = {}
            continue
        total_terms = sum(counts.values())
        weights: dict[str, float] = {}
        norm_sq = 0.0
        for token, count in counts.items():
            tf = count / total_terms
            idf = math.log((1 + total_docs) / (1 + document_frequency[token])) + 1.0
            weight = tf * idf
            weights[token] = weight
            norm_sq += weight * weight
        norm = math.sqrt(norm_sq) or 1.0
        vectors[slug] = {token: weight / norm for token, weight in weights.items()}
    return vectors


def cosine_similarity_sparse(left: dict[str, float], right: dict[str, float]) -> float:
    if not left or not right:
        return 0.0
    if len(left) > len(right):
        left, right = right, left
    return sum(weight * right.get(token, 0.0) for token, weight in left.items())


def render_discovery_links(items: list[dict[str, object]], label: str, safe_text) -> str:
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


def render_version_sections(relation: dict[str, object] | None, safe_text) -> str:
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
    type_labels: dict[str, str],
) -> tuple[list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, object]], list[dict[str, str]]]:
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
        same_family = bool(source_meta.get("family_key")) and str(source_meta.get("family_key")) == str(target.get("family_key", ""))
        if target_slug == source_slug or same_family:
            continue
        if target_slug in ref_seen:
            continue
        ref_seen.add(target_slug)
        ref_items.append({
            "title": target["title"],
            "html_path": target["html_path"],
            "kind_label": type_labels.get(str(target["content_type"]), str(target["kind"]).replace("-", " ").title()),
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
            "kind_label": type_labels.get(str(target["content_type"]), str(target["kind"]).replace("-", " ").title()),
            "score": round(score, 6),
            "slug": target_slug,
        })
        if len(related_items) >= 4:
            break

    read_next_items = related_items[:1]
    related_surface_items = related_items[1:4]

    if str(source_meta.get("kind")) == "authority-essay":
        next_slug = str(source_meta.get("collection_next_slug", "") or "")
        if next_slug and next_slug in metadata_by_slug:
            next_meta = metadata_by_slug[next_slug]
            read_next_items = [{
                "title": next_meta["title"],
                "html_path": next_meta["html_path"],
                "kind_label": "Next in collection",
                "slug": next_slug,
            }]
        else:
            read_next_items = []
        related_surface_items = []
        ref_items = []

    verification_items: list[dict[str, object]] = []
    replication_candidates.sort(key=lambda row: (-row[0], str(row[1]["title"]).lower(), str(row[1]["slug"])))
    for score, target in replication_candidates[:2]:
        verification_items.append({
            "title": target["title"],
            "html_path": target["html_path"],
            "kind_label": type_labels.get(str(target["content_type"]), str(target["kind"]).replace("-", " ").title()),
            "score": round(score, 6),
            "slug": str(target["slug"]),
        })

    if str(source_meta.get("content_type")) == "non-engineering":
        read_next_items = []
        verification_items = []
        related_surface_items = []

    return ref_items, read_next_items, related_surface_items, verification_items, debug_excluded


def build_discovery_sections(
    metadata_index: list[dict[str, object]],
    contexts: dict[str, dict[str, object]],
    type_labels: dict[str, str],
    safe_text,
) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, object]]]:
    version_relations = build_version_relations(metadata_index)
    tfidf_vectors = compute_tfidf_vectors(contexts)
    metadata_by_slug = {str(item["slug"]): item for item in metadata_index}

    rendered: dict[str, dict[str, str]] = {}
    recommendation_artifacts: dict[str, dict[str, object]] = {}

    for item in metadata_index:
        source_slug = str(item["slug"])
        references, read_next_items, related_items, verification_items, debug_excluded = pick_related_candidates(
            item, metadata_by_slug, contexts, tfidf_vectors, version_relations, type_labels
        )

        rendered[source_slug] = {
            "references_html": render_discovery_links(references, "Referenced artifacts", safe_text),
            "read_next_html": render_discovery_links(read_next_items, "Read next", safe_text),
            "related_html": render_discovery_links(related_items, "Related", safe_text),
            "verification_html": render_discovery_links(verification_items, "Verification & replication", safe_text),
            "version_html": render_version_sections(version_relations.get(source_slug), safe_text),
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


def write_recommendation_index(dist_root: Path, recommendation_artifacts: dict[str, dict[str, object]], site_name: str, site_url: str) -> None:
    metadata_dir = dist_root / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "site": site_name,
        "site_url": site_url,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "recommendations": recommendation_artifacts,
    }
    (metadata_dir / "recommendations.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def inject_discovery_sections(
    dist_root: Path,
    metadata_index: list[dict[str, object]],
    contexts: dict[str, dict[str, object]],
    type_labels: dict[str, str],
    safe_text,
    relative_href,
) -> dict[str, dict[str, object]]:
    discovery_sections, recommendation_artifacts = build_discovery_sections(metadata_index, contexts, type_labels, safe_text)
    version_relations = build_version_relations(metadata_index)
    for item in metadata_index:
        source_slug = str(item['slug'])
        section_html = discovery_sections.get(source_slug, {})
        relation = version_relations.get(source_slug)
        footer_html = ''
        if relation and not relation.get('is_latest'):
            family_key = str(relation.get('family_key', ''))
            family_href = relative_href(f'/{item["content_type"]}/{source_slug}/', f'/{item["content_type"]}/{family_key}/')
            footer_html = '<section class="pse-discovery"><h2>Version status</h2><ul class="pse-discovery-list"><li class="pse-discovery-item">This is not the latest version. <a href="' + html.escape(family_href, quote=True) + '">See the latest.</a></li></ul></section>'
        out_path = dist_root / str(item['content_type']) / Path(source_slug) / 'index.html'
        if not out_path.exists():
            continue
        html_text = out_path.read_text(encoding='utf-8')
        html_text = inject_discovery_markup(html_text, [footer_html, section_html.get('version_html', ''), section_html.get('references_html', ''), section_html.get('read_next_html', ''), section_html.get('related_html', ''), section_html.get('verification_html', '')])
        out_path.write_text(html_text, encoding='utf-8')
    return recommendation_artifacts
