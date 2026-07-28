"""Configuration loading and validation."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from bhava_library.constants import (
    DEFAULT_BATCH_CAP_GIB,
    DEFAULT_CHUNK_MIB,
    DEFAULT_MAX_FILE_GIB,
    DEFAULT_RESERVE_GIB,
    DEFAULT_RESERVE_PERCENT,
    USER_AGENT_DEFAULT,
)
from bhava_library.domain.errors import ConfigError

# Corrected owner identity (never use obsolete Swarna* spellings in new config).
COPYRIGHT_OWNER = "Svarna Gauranga Das"
COPYRIGHT_PUBLISHER = "Dauji Publication"
COPYRIGHT_PROJECT = "Bhāva"
COPYRIGHT_LOCATION = "Harrisburg, Pennsylvania, USA"
COPYRIGHT_EMAIL = "svarnagaurangdas@gmail.com"


def find_repo_root(start: Path | None = None) -> Path:
    """Walk upward until pyproject.toml / bhava.ps1 is found."""
    cur = (start or Path.cwd()).resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / "pyproject.toml").exists() and (candidate / "bhava.ps1").exists():
            return candidate
        if (candidate / "pyproject.toml").exists() and (
            candidate / "config" / "default.toml"
        ).exists():
            return candidate
    raise ConfigError(f"Could not locate bhava-library repository root from {cur}")


class CopyrightConfig(BaseModel):
    owner: str = COPYRIGHT_OWNER
    publisher: str = COPYRIGHT_PUBLISHER
    project: str = COPYRIGHT_PROJECT
    location: str = COPYRIGHT_LOCATION
    contact_email: str = COPYRIGHT_EMAIL
    phone: str = ""

    @field_validator("owner")
    @classmethod
    def owner_must_be_svarna(cls, v: str) -> str:
        # Normalize obsolete package spelling if somehow present.
        if v.strip().lower().replace(" ", "") in {
            "swarnagaurangadas",
            "svarnagaurangadas",
        }:
            return COPYRIGHT_OWNER
        if "swarna" in v.lower():
            return COPYRIGHT_OWNER
        return v

    @field_validator("contact_email")
    @classmethod
    def email_must_be_corrected(cls, v: str) -> str:
        lowered = v.strip().lower()
        if "swarna" in lowered or lowered == "svarnagaurangadas@gmail.com":
            # Keep svarnagaurangdas (correct) vs swarna*
            if lowered == COPYRIGHT_EMAIL.lower():
                return COPYRIGHT_EMAIL
            if "swarna" in lowered:
                return COPYRIGHT_EMAIL
        return v.strip() or COPYRIGHT_EMAIL


class SourceConfig(BaseModel):
    enabled: bool = True
    index_url: str = "https://iskconeducation.org/media_library/"
    user_agent: str = USER_AGENT_DEFAULT
    request_delay_seconds: float = 2.0
    max_connections_per_host: int = 1
    max_global_downloads: int = 2
    follow_external_direct_files: bool = True
    allow_authentication: bool = False


class DownloadConfig(BaseModel):
    default_profile: str = "core"
    initial_batch_cap_gib: float = DEFAULT_BATCH_CAP_GIB
    max_file_gib: float = DEFAULT_MAX_FILE_GIB
    chunk_mib: float = DEFAULT_CHUNK_MIB
    reserve_gib: float = DEFAULT_RESERVE_GIB
    reserve_percent: float = DEFAULT_RESERVE_PERCENT
    temporary_overhead_percent: float = 10
    temporary_overhead_gib: float = 2
    resume: bool = True
    verify_tls: bool = True
    audio_enabled: bool = False
    video_enabled: bool = False


class VerificationConfig(BaseModel):
    sha256: bool = True
    content_length: bool = True
    signature_detection: bool = True
    windows_defender: bool = True
    mark_verified_read_only: bool = True
    destructive_deduplication: bool = False


class ProjectConfig(BaseModel):
    name: str = "Bhāva Library"
    slug: str = "bhava-library"
    data_dir: str = "data"
    timezone: str = "America/New_York"


class BackupConfig(BaseModel):
    target: str | None = None


class PathsConfig(BaseModel):
    data_dir: str | None = None


class Settings(BaseModel):
    repo_root: Path
    project: ProjectConfig = Field(default_factory=ProjectConfig)
    source_iskcon: SourceConfig = Field(default_factory=SourceConfig)
    download: DownloadConfig = Field(default_factory=DownloadConfig)
    verification: VerificationConfig = Field(default_factory=VerificationConfig)
    copyright: CopyrightConfig = Field(default_factory=CopyrightConfig)
    backup: BackupConfig = Field(default_factory=BackupConfig)
    paths: PathsConfig = Field(default_factory=PathsConfig)

    @property
    def data_dir(self) -> Path:
        override = self.paths.data_dir
        raw = override or self.project.data_dir
        path = Path(raw)
        if not path.is_absolute():
            path = self.repo_root / path
        return path

    @property
    def catalog_db(self) -> Path:
        return self.data_dir / "catalog" / "bhava-library.sqlite3"

    @property
    def originals_dir(self) -> Path:
        return self.data_dir / "originals" / "iskcon-education"

    @property
    def staging_dir(self) -> Path:
        return self.data_dir / "staging"

    @property
    def quarantine_dir(self) -> Path:
        return self.data_dir / "quarantine"

    @property
    def snapshots_dir(self) -> Path:
        return self.data_dir / "snapshots"

    @property
    def reports_dir(self) -> Path:
        return self.repo_root / "reports" / "generated"

    @property
    def manifests_dir(self) -> Path:
        return self.repo_root / "manifests"

    @property
    def copyright_dir(self) -> Path:
        return self.repo_root / "copyright"

    @property
    def logs_dir(self) -> Path:
        return self.repo_root / "logs"


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load_settings(repo_root: Path | None = None) -> Settings:
    """Load default.toml then optional local.toml overlays."""
    root = repo_root or find_repo_root()
    default_path = root / "config" / "default.toml"
    local_path = root / "config" / "local.toml"
    raw = _load_toml(default_path)
    raw = _deep_merge(raw, _load_toml(local_path))

    source_section = raw.get("source", {}).get("iskcon_education", {})
    # Normalize user_agent email if obsolete spelling appears in package leftovers.
    ua = source_section.get("user_agent", USER_AGENT_DEFAULT)
    if "SwarnaGaurangaDas" in ua or "swarnagaurangadas" in ua.lower():
        source_section = {
            **source_section,
            "user_agent": USER_AGENT_DEFAULT,
        }

    copyright_raw = raw.get("copyright", {})
    settings = Settings(
        repo_root=root,
        project=ProjectConfig(**raw.get("project", {})),
        source_iskcon=SourceConfig(**source_section),
        download=DownloadConfig(**raw.get("download", {})),
        verification=VerificationConfig(**raw.get("verification", {})),
        copyright=CopyrightConfig(**copyright_raw),
        backup=BackupConfig(**raw.get("backup", {})),
        paths=PathsConfig(**raw.get("paths", {})),
    )
    # Force corrected identity regardless of stale template values.
    settings.copyright.owner = COPYRIGHT_OWNER
    settings.copyright.publisher = COPYRIGHT_PUBLISHER
    settings.copyright.project = COPYRIGHT_PROJECT
    settings.copyright.location = COPYRIGHT_LOCATION
    settings.copyright.contact_email = COPYRIGHT_EMAIL
    settings.copyright.phone = ""
    return settings
