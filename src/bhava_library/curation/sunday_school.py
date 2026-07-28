"""Sunday-school program mappings and educational profiles."""

from __future__ import annotations

import json

from bhava_library.config import Settings
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
    "worksheet": "printables-worksheets",
    "lesson-plan": "teacher-lesson-plans",
    "teacher-guide": "teacher-guides",
    "comic": "story-comics",
    "audio-story": "audio-stories",
    "quiz": "assessments",
}


def _age_from_audience(audience_term: str) -> tuple[int | None, int | None]:
    return AGE_BANDS.get(audience_term, (None, None))


def run_sunday_school(settings: Settings, *, limit: int | None = None) -> dict[str, int]:
    db = Database(settings.catalog_db)
    db.migrate()
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
                "audience_terms": audience_terms,
                "content_forms": form_terms,
                "program_terms": program_terms,
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
                (rid, age_min, age_max, None, None, json.dumps(payload)),
            )
            profiles += 1

            collections: set[str] = set()
            for form in form_terms:
                coll = FORM_COLLECTIONS.get(form)
                if coll:
                    collections.add(coll)
            if "sunday-school" in program_terms or any(
                t in {"sunday-school", "bal-gopal"} for t in program_terms
            ):
                collections.add("sunday-school-core")
            if not collections:
                collections.add("general-reference")

            for coll in sorted(collections):
                conn.execute(
                    """
                    INSERT INTO program_mappings(resource_id, program, collection, assumptions_json, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (
                        rid,
                        "sunday-school",
                        coll,
                        json.dumps({"age_min": age_min, "age_max": age_max}),
                        utc_now(),
                    ),
                )
                mappings += 1

    return {"profiles": profiles, "mappings": mappings}
