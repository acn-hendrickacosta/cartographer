"""Project registry: an index of projects a developer has worked on, used for
cross-project recall (PROJECT_BRIEF.md Section 4, 7.3).

Location default: per-user-home (`~/.cartographer/registry.json`). This is a working
default, not a resolved decision -- open question #5 in PROJECT_BRIEF.md Section 14
asks whether it should instead be per-machine. Kept behind this module so relocating
later is a one-line change, not a rewrite.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel


class ProjectRecord(BaseModel):
    project_id: str
    name: str
    topology: str
    tenant: str
    created_at: str
    last_indexed_at: str
    location: str


def registry_path() -> Path:
    return Path.home() / ".cartographer" / "registry.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_registry() -> dict[str, ProjectRecord]:
    path = registry_path()
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    return {pid: ProjectRecord(**record) for pid, record in raw.items()}


def save_registry(records: dict[str, ProjectRecord]) -> Path:
    path = registry_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {pid: record.model_dump() for pid, record in records.items()}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return path


def register_project(
    project_id: str,
    name: str,
    topology: str,
    tenant: str,
    location: Path,
) -> ProjectRecord:
    """Upsert a project record. Idempotent: re-registering the same project_id
    updates in place rather than duplicating."""
    records = load_registry()
    existing = records.get(project_id)
    record = ProjectRecord(
        project_id=project_id,
        name=name,
        topology=topology,
        tenant=tenant,
        created_at=existing.created_at if existing else _now(),
        last_indexed_at=_now(),
        location=str(location.resolve()),
    )
    records[project_id] = record
    save_registry(records)
    return record


def get_project(project_id: str) -> ProjectRecord | None:
    return load_registry().get(project_id)


def list_projects(tenant: str | None = None) -> list[ProjectRecord]:
    """List registered projects, optionally filtered to a single tenant.

    There is deliberately no "all tenants" query path in the recall skill; this
    function exists for that filtered lookup, not as a way to enumerate everything.
    """
    records = list(load_registry().values())
    if tenant is None:
        return records
    return [r for r in records if r.tenant == tenant]
