"""Sunday-school program mappings and educational profiles."""

from __future__ import annotations

import json

from bhava_library.config import Settings
from bhava_library.curation.program_config import ProgramDefinition, load_programs
from bhava_library.infrastructure.database import Database, utc_now

AGE_BANDS: dict[str, tuple[int, int]] = {
    "ages-3-5": (3, 5),
    "ages-4-7": (4, 7),
    "ages-5-7": (5, 7),
    "ages-6-8": (6, 8),
    "ages-7-9": (7, 9),
    "ages-8-11": (8, 11),
    "ages-9-12": (9, 12),
    "ages-9-13": (9, 13),
    "ages-11-14": (11, 14),
}

FORM_COLLECTIONS: dict[str, str] = {
    "coloring-page": "printables-coloring",
    "coloring-book": "coloring-books",
    "activity-book": "activity-books",
    "worksheet": "printables-worksheets",
    "curriculum": "curricula",
    "syllabus": "syllabi",
    "lesson-plan": "teacher-lesson-plans",
    "teacher-guide": "teacher-guides",
    "comic": "story-comics",
    "illustrated-storybook": "storybooks",
    "audio-story": "audio-stories",
    "quiz": "assessments",
    "presentation": "presentations",
    "craft": "crafts",
    "game": "games",
}


def _age_from_audience(audience_term: str) -> tuple[int | None, int | None]:
    return AGE_BANDS.get(audience_term, (None, None))


def _program_payload(
    definition: ProgramDefinition, age_min: int | None, age_max: int | None
) -> str:
    return json.dumps(
        {
            "configured_age_min": definition.age_min,
            "configured_age_max": definition.age_max,
            "duration_minutes": definition.duration_minutes,
            "purpose": definition.purpose,
            "teacher_prep": definition.teacher_prep,
            "assumptions": definition.assumptions,
            "resource_age_min": age_min,
            "resource_age_max": age_max,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _age_overlap(age_min: int | None, age_max: int | None, definition: ProgramDefinition) -> bool:
    if age_min is None or age_max is None:
        return True
    return age_min <= definition.age_max and age_max >= definition.age_min


def _matching_programs(
    programs: dict[str, ProgramDefinition],
    program_terms: list[str],
    form_terms: list[str],
    age_min: int | None,
    age_max: int | None,
) -> dict[str, tuple[ProgramDefinition, str]]:
    """Return program key -> (definition, match_reason)."""
    matched: dict[str, tuple[ProgramDefinition, str]] = {}
    explicit = set(program_terms)
    for definition in programs.values():
        if definition.classification_term in explicit:
            matched[definition.key] = (definition, "explicit-program-use")
    if matched:
        return matched
    # Suitability fallback for general educational materials.
    for definition in programs.values():
        form_hit = any(form in definition.forms for form in form_terms)
        if not form_hit:
            continue
        if not _age_overlap(age_min, age_max, definition):
            continue
        matched[definition.key] = (definition, "form-age-suitability")
    return matched


def run_sunday_school(settings: Settings, *, limit: int | None = None) -> dict[str, int]:
    db = Database(settings.catalog_db)
    db.migrate()
    programs = load_programs(settings.repo_root / "config" / "programs.toml")
    sql = """
        SELECT rc.resource_id, rc.dimension, rc.term
        FROM resource_classifications rc
        JOIN resources r ON r.resource_id = rc.resource_id
        WHERE r.removed_at IS NULL
          AND rc.dimension IN ('audience', 'content-form', 'program-use')
        ORDER BY rc.resource_id
    """
    rows = db.execute(sql)
    by_resource: dict[str, dict[str, list[str]]] = {}
    for row in rows:
        rid = row["resource_id"]
        by_resource.setdefault(rid, {}).setdefault(row["dimension"], []).append(row["term"])

    if limit is not None:
        keys = list(by_resource.keys())[:limit]
        by_resource = {k: by_resource[k] for k in keys}

    profiles = 0
    mappings = 0
    with db.session() as conn:
        for rid, dims in by_resource.items():
            audience_terms = dims.get("audience", ["unknown"])
            form_terms = dims.get("content-form", ["unknown"])
            program_terms = dims.get("program-use", [])

            age_min: int | None = None
            age_max: int | None = None
            for aud in audience_terms:
                lo, hi = _age_from_audience(aud)
                if lo is not None and hi is not None:
                    age_min = lo if age_min is None else min(age_min, lo)
                    age_max = hi if age_max is None else max(age_max, hi)

            payload = {
                "audience_terms": sorted(audience_terms),
                "content_forms": sorted(form_terms),
                "program_terms": sorted(program_terms),
            }
            conn.execute(
                """
                INSERT INTO educational_profiles(
                  resource_id, age_min, age_max, reading_level, duration_minutes, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(resource_id) DO UPDATE SET
                  age_min = excluded.age_min,
                  age_max = excluded.age_max,
                  payload_json = excluded.payload_json
                """,
                (
                    rid,
                    age_min,
                    age_max,
                    None,
                    None,
                    json.dumps(payload, sort_keys=True, separators=(",", ":")),
                ),
            )
            profiles += 1

            desired: dict[tuple[str, str, str], tuple[str, str]] = {}
            matched = _matching_programs(programs, program_terms, form_terms, age_min, age_max)
            for definition, match_reason in matched.values():
                collections = {
                    FORM_COLLECTIONS[form]
                    for form in form_terms
                    if form in definition.forms and form in FORM_COLLECTIONS
                }
                if not collections:
                    collections = {f"{definition.key}-core"}
                base = json.loads(_program_payload(definition, age_min, age_max))
                base["match_reason"] = match_reason
                assumptions = json.dumps(base, sort_keys=True, separators=(",", ":"))
                for collection in collections:
                    key = (definition.key, collection, definition.version)
                    desired[key] = (assumptions, definition.version)

            versions = sorted({definition.version for definition in programs.values()})
            for version in versions:
                existing = conn.execute(
                    """
                    SELECT program, collection, mapping_version
                    FROM program_mappings
                    WHERE resource_id = ? AND mapping_version = ?
                    """,
                    (rid, version),
                ).fetchall()
                for old in existing:
                    key = (old["program"], old["collection"], old["mapping_version"])
                    if key not in desired:
                        conn.execute(
                            """
                            DELETE FROM program_mappings
                            WHERE resource_id = ? AND program = ? AND collection = ?
                              AND mapping_version = ?
                            """,
                            (rid, *key),
                        )
            # Drop legacy rows that predate mapping_version.
            conn.execute(
                """
                DELETE FROM program_mappings
                WHERE resource_id = ? AND (mapping_version IS NULL OR mapping_version = '')
                """,
                (rid,),
            )

            for (program, coll, version), (assumptions, _) in sorted(desired.items()):
                conn.execute(
                    """
                    INSERT INTO program_mappings(
                      resource_id, program, collection, assumptions_json, created_at, mapping_version
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(resource_id, program, collection, mapping_version) DO UPDATE SET
                      assumptions_json = excluded.assumptions_json
                    """,
                    (
                        rid,
                        program,
                        coll,
                        assumptions,
                        utc_now(),
                        version,
                    ),
                )
                mappings += 1

    return {"profiles": profiles, "mappings": mappings}
