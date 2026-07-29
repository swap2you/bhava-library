"""Deterministic taxonomy classification with evidence."""

from __future__ import annotations

import json
import re
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from bhava_library.config import Settings
from bhava_library.curation.taxonomy_seed import RULE_VERSION
from bhava_library.infrastructure.database import Database, utc_now

REVIEW_THRESHOLD = 0.55


@dataclass(frozen=True)
class ClassificationHit:
    dimension: str
    term: str
    confidence: float
    excerpt: str
    classifier: str


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()


def _match_any(text: str, patterns: list[tuple[str, str, float]]) -> ClassificationHit | None:
    for term, pattern, confidence in patterns:
        if re.search(pattern, text, re.IGNORECASE):
            return ClassificationHit("auto", term, confidence, pattern, "regex")
    return None


def _match_all(
    dimension: str, text: str, patterns: list[tuple[str, str, float]]
) -> list[ClassificationHit]:
    return [
        ClassificationHit(dimension, term, confidence, pattern, "regex")
        for term, pattern, confidence in patterns
        if re.search(pattern, text, re.IGNORECASE)
    ]


def _content_form(text: str) -> ClassificationHit:
    rules: list[tuple[str, str, float]] = [
        ("coloring-book", r"\bcolou?r(?:ing)?[\s_-]*book\b", 0.94),
        ("coloring-page", r"\bcolou?r(?:ing)?[\s_-]*(?:page|sheet)\b", 0.92),
        ("curriculum", r"\bcurricul(?:um|a)\b|course\s+of\s+study", 0.91),
        ("syllabus", r"\bsyllabus\b", 0.92),
        ("activity-book", r"\bactivity[\s_-]*book\b", 0.92),
        ("illustrated-storybook", r"\b(?:illustrated\s+)?story[\s_-]*book\b", 0.9),
        ("worksheet", r"worksheet|activity\s*sheet", 0.88),
        ("crossword", r"crossword", 0.9),
        ("word-search", r"word\s*search", 0.9),
        ("connect-the-dots", r"connect\s*(?:the\s*)?dots?|dot[\s_-]*to[\s_-]*dot", 0.9),
        ("maze", r"\bmazes?\b", 0.9),
        ("matching", r"\bmatch(?:ing)?\s+(?:game|activity|exercise|pairs?)\b", 0.86),
        ("sequencing", r"\bsequenc(?:e|ing)\s+(?:cards?|activity|events?)\b", 0.86),
        ("lesson-plan", r"lesson\s*plan", 0.88),
        ("teacher-guide", r"teacher('s|)\s*guide|teachers\s*guide", 0.88),
        ("student-workbook", r"workbook|student\s*book", 0.85),
        ("comic", r"\bcomic\b", 0.85),
        ("drama-script", r"\b(?:drama|play|skit)\s*(?:script)?\b", 0.88),
        ("song-lyrics", r"\b(?:song\s*)?lyrics?\b", 0.88),
        ("prayer-audio", r"\bprayer\b.*\b(?:mp3|wav|audio)\b|\baudio\b.*\bprayer\b", 0.9),
        ("drama-audio", r"\b(?:drama|play)\b.*\b(?:mp3|wav|audio)\b", 0.88),
        ("pronunciation-audio", r"\bpronunciation\b.*\b(?:mp3|wav|audio)\b", 0.88),
        ("curriculum-audio", r"\bcurricul(?:um|a)\b.*\b(?:mp3|wav|audio)\b", 0.86),
        ("audio-story", r"audio\s*story|story\s*audio|audiobook", 0.88),
        ("lecture-audio", r"\b(?:lecture|seminar|class)\b.*\b(?:mp3|wav|audio)\b", 0.84),
        ("kirtan", r"\bkirtan\b", 0.86),
        ("bhajan", r"\bbhajan\b", 0.86),
        ("prayer", r"\bprayer\b|\bpranama\b", 0.82),
        ("presentation", r"\bpresentation\b|power\s*point|\bpptx?\b|slide\s*deck", 0.88),
        ("poster", r"\bposter\b", 0.8),
        ("flashcard", r"flash\s*card", 0.85),
        ("craft", r"\bcraft\b", 0.78),
        ("game", r"\bgames?\b", 0.8),
        ("quiz", r"\bquiz\b|assessment", 0.82),
        ("archive-bundle", r"\.zip$|archive|bundle", 0.7),
    ]
    hit = _match_any(text, rules)
    if hit:
        return ClassificationHit(
            "content-form", hit.term, hit.confidence, hit.excerpt, hit.classifier
        )
    if re.search(r"\.pdf$", text):
        return ClassificationHit("content-form", "reference-book", 0.5, ".pdf", "extension")
    return ClassificationHit("content-form", "unknown", 0.3, text[:80], "fallback")


def _audience(text: str) -> ClassificationHit:
    rules: list[tuple[str, str, float]] = [
        ("ages-3-5", r"ages?\s*3[-–]5|3[-–]5\s*years?", 0.9),
        ("ages-4-7", r"ages?\s*4[-–]7|4[-–]7\s*years?", 0.9),
        ("ages-5-7", r"ages?\s*5[-–]7|5[-–]7\s*years?", 0.9),
        ("ages-6-8", r"ages?\s*6[-–]8|6[-–]8\s*years?", 0.9),
        ("ages-7-9", r"ages?\s*7[-–]9|7[-–]9\s*years?", 0.9),
        ("ages-8-11", r"ages?\s*8[-–]11|8[-–]11\s*years?", 0.9),
        ("ages-9-12", r"ages?\s*9[-–]12|9[-–]12\s*years?", 0.9),
        ("youth", r"\byouth\b|teen", 0.82),
        ("teacher", r"\bteacher\b|educator", 0.78),
        ("parent", r"\bparent\b|family", 0.75),
        ("adult", r"\badult\b", 0.7),
    ]
    hit = _match_any(text, rules)
    if hit:
        return ClassificationHit("audience", hit.term, hit.confidence, hit.excerpt, hit.classifier)
    return ClassificationHit("audience", "unknown", 0.35, text[:80], "fallback")


def _program_use(text: str) -> list[ClassificationHit]:
    rules: list[tuple[str, str, float]] = [
        ("sunday-school", r"sunday\s*school|ss\s*class", 0.9),
        ("bal-gopal", r"bal\s*gopal", 0.9),
        ("damodara-class", r"damodara\s*(?:class|program)", 0.9),
        ("gopinath-class", r"gopinath\s*(?:class|program)", 0.9),
        ("gurukula", r"gurukula", 0.88),
        ("homeschool", r"home\s*school", 0.85),
        ("family-bhakti", r"family\s*bhakti|family\s*devotion", 0.87),
        ("festival-program", r"festival", 0.75),
        ("youth-program", r"\byouth\b|\bteen", 0.82),
    ]
    hits = _match_all("program-use", text, rules)
    return hits or [
        ClassificationHit("program-use", "general-reference", 0.45, text[:80], "fallback")
    ]


def _topic(text: str) -> list[ClassificationHit]:
    rules: list[tuple[str, str, float]] = [
        ("krishna", r"\bkrishna\b", 0.88),
        ("balarama", r"\bbalarama\b", 0.88),
        ("radha", r"\bRadha\b|\bRadharani\b", 0.88),
        ("caitanya-mahaprabhu", r"caitanya|gaura", 0.85),
        ("srila-prabhupada", r"prabhupada", 0.85),
        ("bhagavad-gita", r"bhagavad\s*gita|bg\s*\d", 0.9),
        ("srimad-bhagavatam", r"bhagavatam|srimad\s*Bhag", 0.88),
        ("krishna-book", r"krishna\s*book", 0.88),
        ("holy-name", r"holy\s*name|japa|mantra", 0.8),
        ("kirtan", r"kirtan|bhajan", 0.78),
        ("festivals", r"festival|janmastami|gaura\s*purnima", 0.75),
        ("values", r"values|character", 0.7),
    ]
    return _match_all("topic", text, rules) or [
        ClassificationHit("topic", "devotional-practice", 0.4, text[:80], "fallback")
    ]


def _festival(text: str) -> list[ClassificationHit]:
    rules: list[tuple[str, str, float]] = [
        ("janmastami", r"janmastami|janmashtami", 0.92),
        ("radhastami", r"radhastami", 0.92),
        ("gaura-purnima", r"gaura\s*purnima", 0.92),
        ("nrsimha-caturdasi", r"nrsimha|narasimha", 0.9),
        ("rama-navami", r"rama\s*navami", 0.9),
        ("govardhana-puja", r"govardhana", 0.9),
        ("dipavali", r"dipavali|diwali", 0.88),
        ("damodara-month", r"damodara|kartik", 0.85),
        ("ratha-yatra", r"ratha\s*yatra", 0.9),
    ]
    return _match_all("festival", text, rules)


def _person(text: str) -> list[ClassificationHit]:
    return _match_all(
        "person",
        text,
        [
            ("krishna", r"\bkrishna\b", 0.9),
            ("balarama", r"\bbalarama\b", 0.9),
            ("radha", r"\bradha(?:rani)?\b", 0.9),
            ("caitanya-mahaprabhu", r"\b(?:caitanya|chaitanya|gauranga)\b", 0.88),
            ("nityananda", r"\bnityananda\b", 0.9),
            ("srila-prabhupada", r"\bprabhupada\b", 0.9),
        ],
    )


def _language(lang_field: str | None, text: str) -> ClassificationHit:
    if lang_field:
        norm = _norm(lang_field)
        mapping = {
            "english": "english",
            "en": "english",
            "hindi": "hindi",
            "bengali": "bengali",
            "sanskrit": "sanskrit",
            "spanish": "spanish",
        }
        values = {value.strip() for value in re.split(r"[,;/|]", norm)}
        for key, term in mapping.items():
            if key in values:
                return ClassificationHit("language", term, 0.9, lang_field, "catalog-field")
    if re.search(r"\bhindi\b", text, re.I):
        return ClassificationHit("language", "hindi", 0.7, "hindi", "regex")
    return ClassificationHit("language", "unknown", 0.3, text[:40], "fallback")


def _scripture(text: str) -> ClassificationHit:
    rules: list[tuple[str, str, float]] = [
        ("bhagavad-gita", r"bhagavad\s*gita", 0.9),
        ("srimad-bhagavatam-canto-chapter", r"bhagavatam|canto", 0.85),
        ("krishna-book-chapter", r"krishna\s*book", 0.85),
        ("caitanya-caritamrta", r"caitanya\s*carit", 0.88),
        ("prabhupada-lecture", r"prabhupada.*lecture|lecture.*prabhupada", 0.82),
    ]
    hit = _match_any(text, rules)
    if hit:
        return ClassificationHit("scripture", hit.term, hit.confidence, hit.excerpt, hit.classifier)
    return ClassificationHit("scripture", "unknown", 0.35, text[:80], "fallback")


def _production_opportunity(form: str, confidence: float) -> ClassificationHit:
    mapping = {
        "coloring-page": "printable-candidate",
        "worksheet": "activity-candidate",
        "comic": "original-comic-candidate",
        "lesson-plan": "teacher-guide-candidate",
        "teacher-guide": "teacher-guide-candidate",
        "audio-story": "audio-remaster-candidate",
        "unknown": "needs-source-verification",
    }
    term = mapping.get(form, "useful-reference")
    conf = min(0.95, max(0.4, confidence))
    return ClassificationHit("production-opportunity", term, conf, form, "form-map")


def _reference_boundary() -> ClassificationHit:
    return ClassificationHit(
        "reference-boundary",
        "facts-only",
        0.85,
        "third-party-acquired",
        "policy-default",
    )


def classify_resource(row: dict[str, object]) -> list[ClassificationHit]:
    title = str(row.get("title_original") or "")
    rel = str(row.get("relative_path") or "")
    filename = Path(rel).name if rel else ""
    media_type = str(row.get("media_type") or "")
    media_format = str(row.get("media_format") or "")
    profile = str(row.get("profile") or "")
    source_label = str(row.get("source_label") or "")
    theme = str(row.get("theme") or "")
    technical = str(row.get("technical_metadata_json") or "")
    with suppress(TypeError, ValueError):
        technical = json.dumps(json.loads(technical), sort_keys=True) if technical else ""
    language = row.get("language")
    blob = _norm(
        f"{title} {filename} {media_type} {media_format} {profile} "
        f"{source_label} {theme} {technical}"
    )

    hits: list[ClassificationHit] = []
    form = _content_form(blob)
    hits.append(form)
    hits.append(_audience(blob))
    hits.extend(_program_use(blob))
    hits.extend(_topic(blob))
    hits.extend(_person(blob))
    hits.extend(_festival(blob))
    hits.append(_language(str(language) if language else None, blob))
    hits.append(_scripture(blob))
    hits.append(_production_opportunity(form.term, form.confidence))
    hits.append(_reference_boundary())
    return list({(hit.dimension, hit.term): hit for hit in hits}.values())


def _review_state(confidence: float) -> str:
    if confidence < REVIEW_THRESHOLD:
        return "needs_review"
    return "auto_accepted"


def _store_classification(conn, resource_id: str, hit: ClassificationHit) -> None:
    review = _review_state(hit.confidence)
    conn.execute(
        """
        INSERT INTO resource_classifications(
          resource_id, dimension, term, confidence, source, rule_version, review_state, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(resource_id, dimension, term) DO UPDATE SET
          confidence = excluded.confidence,
          source = excluded.source,
          rule_version = excluded.rule_version,
          review_state = excluded.review_state
        """,
        (
            resource_id,
            hit.dimension,
            hit.term,
            hit.confidence,
            hit.classifier,
            RULE_VERSION,
            review,
            utc_now(),
        ),
    )
    conn.execute(
        """
        INSERT INTO classification_evidence(
          resource_id, dimension, term, classifier, excerpt, confidence, rule_version, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(resource_id, dimension, term, classifier, rule_version) DO UPDATE SET
          excerpt = excluded.excerpt,
          confidence = excluded.confidence
        """,
        (
            resource_id,
            hit.dimension,
            hit.term,
            hit.classifier,
            hit.excerpt,
            hit.confidence,
            RULE_VERSION,
            utc_now(),
        ),
    )


def run_classify(settings: Settings, *, limit: int | None = None) -> dict[str, int]:
    db = Database(settings.catalog_db)
    db.migrate()
    sql = """
        SELECT r.resource_id, r.title_original, r.media_type, r.media_format,
               r.profile, r.language, r.source_label, r.theme,
               (SELECT MIN(lf.relative_path) FROM local_files lf
                WHERE lf.resource_id = r.resource_id) AS relative_path,
               tm.payload_json AS technical_metadata_json
        FROM resources r
        LEFT JOIN technical_metadata tm ON tm.resource_id = r.resource_id
        WHERE r.removed_at IS NULL
        ORDER BY r.resource_id
    """
    params: tuple[()] | tuple[int] = ()
    if limit is not None:
        sql += " LIMIT ?"
        params = (limit,)
    rows = db.execute(sql, params)
    classified = 0
    labels = 0
    with db.session() as conn:
        for row in rows:
            hits = classify_resource(dict(row))
            conn.execute(
                "DELETE FROM classification_evidence WHERE resource_id = ?",
                (row["resource_id"],),
            )
            conn.execute(
                "DELETE FROM resource_classifications WHERE resource_id = ?",
                (row["resource_id"],),
            )
            for hit in hits:
                _store_classification(conn, row["resource_id"], hit)
                labels += 1
            classified += 1
    return {"resources": len(rows), "classified": classified, "labels": labels}
