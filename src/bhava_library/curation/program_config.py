"""Versioned, configurable educational program definitions."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProgramDefinition:
    key: str
    classification_term: str
    age_min: int
    age_max: int
    purpose: str
    forms: tuple[str, ...]
    duration_minutes: int
    teacher_prep: str
    assumptions: tuple[str, ...]
    version: str


def load_programs(path: Path) -> dict[str, ProgramDefinition]:
    """Load program definitions from TOML and reject duplicate keys."""
    with path.open("rb") as handle:
        raw = tomllib.load(handle)
    programs: dict[str, ProgramDefinition] = {}
    for item in raw.get("programs", []):
        definition = ProgramDefinition(
            key=item["key"],
            classification_term=item["classification_term"],
            age_min=item["age_min"],
            age_max=item["age_max"],
            purpose=item["purpose"],
            forms=tuple(item["forms"]),
            duration_minutes=item["duration_minutes"],
            teacher_prep=item["teacher_prep"],
            assumptions=tuple(item["assumptions"]),
            version=item["version"],
        )
        if definition.key in programs:
            raise ValueError(f"Duplicate program key: {definition.key}")
        if definition.age_min > definition.age_max:
            raise ValueError(f"Invalid age range for program: {definition.key}")
        programs[definition.key] = definition
    return programs
