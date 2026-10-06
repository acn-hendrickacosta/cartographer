"""Reads from (and, as of SR.3, writes to) the private Standards Registry S3
bucket (SR.1) server-side.

Nothing in this module is ever exposed as a direct S3 URL to a caller --
every function here returns data the route handlers assemble into a
response. This is the one place in the application that talks to S3 at all.

**Extended 2026-10-05** to cover all three content types a pack can publish --
standards, skills, agents -- not just standards. Each is independently
optional per pack (e.g. "core" has no standards at all; "angular" has no
stack-specific agents). Skills archives preserve one level of subdirectory
nesting (<skill-name>/SKILL.md); standards and agents are flat -- same
distinction as cartographer/standards_registry.py's extract_pack_zip vs.
extract_skills_zip on the CLI side.

**Extended again (SR.3)** with publish-side writes: build_zip_from_files
treats skills/standards/agents uniformly (zipfile.writestr happily accepts
"/" in an arcname and creates the nested structure on extraction either way),
so the asymmetry between content types only matters when *reading* an
existing archive (list_files_in_zip vs. list_skills_in_zip group differently),
not when writing a new one.

**Extended again (SR.5)** with an optional `project_id` on get_latest/
get_content_zip/put_content_zip/put_latest, so the same key-shaped layout can
host a per-project fork at "projects/<project_id>/packs/..." alongside the
global baseline at "packs/...". Forks always use FORK_VERSION rather than a
real semver -- they don't carry a version history (see
fork_pack_for_project's docstring) -- so version.json/get_version_metadata/
list_versions stay global-only and are untouched by this.
"""

from __future__ import annotations

import json
import zipfile
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Literal

import boto3
from botocore.exceptions import ClientError

from app.settings import settings

ContentType = Literal["standards", "skills", "agents"]
CONTENT_TYPES: tuple[ContentType, ...] = ("standards", "skills", "agents")

# Fixed marker version for a per-project fork (SR.5) -- not a real semver.
# A fork has exactly one live state; pushing to it overwrites that state
# rather than creating a new version. See fork_pack_for_project.
FORK_VERSION = "fork"

_s3 = boto3.client("s3", region_name=settings.aws_region)


def _prefix(project_id: str | None) -> str:
    return "packs/" if project_id is None else f"projects/{project_id}/packs/"

# boto3 calls are blocking; this pool lets the route handlers below fetch each
# pack's latest.json concurrently instead of one-at-a-time. See
# list_registry_index's docstring for why this exists.
_io_pool = ThreadPoolExecutor(max_workers=16)


def list_packs() -> list[str]:
    paginator = _s3.get_paginator("list_objects_v2")
    names: list[str] = []
    for page in paginator.paginate(Bucket=settings.registry_bucket, Prefix="packs/", Delimiter="/"):
        for prefix in page.get("CommonPrefixes", []):
            # prefix["Prefix"] looks like "packs/python/"
            names.append(prefix["Prefix"].split("/")[1])
    return sorted(names)


def list_registry_index() -> dict[str, dict[str, set[str]]]:
    """One paginated LIST across the entire bucket, parsed into
    {pack_name: {version: {content_types_present}}}.

    **Why this exists:** GET /api/packs used to call get_latest() +
    available_content_types() per pack -- 1 GET + up to 3 HEAD requests each,
    all sequential -- which for 13 packs meant up to 52 blocking round-trips
    for a single page load. That's what made the UI "load super slow" when
    this was first built. One LIST call (typically one page; this bucket has
    ~65 objects, well under the 1000-key page size) replaces all the
    HEAD-based existence checks; only the per-pack latest.json GETs remain,
    and those are now dispatched concurrently via _io_pool (see api_packs)."""
    index: dict[str, dict[str, set[str]]] = {}
    paginator = _s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=settings.registry_bucket, Prefix="packs/"):
        for obj in page.get("Contents", []):
            parts = obj["Key"].split("/")
            if len(parts) == 4 and parts[3].endswith(".zip"):
                pack_name, version, filename = parts[1], parts[2], parts[3]
                index.setdefault(pack_name, {}).setdefault(version, set()).add(filename.removesuffix(".zip"))
            elif len(parts) >= 2 and parts[1]:
                index.setdefault(parts[1], {})
    return index


def get_latest_many(pack_names: list[str]) -> dict[str, dict | None]:
    """get_latest() for several packs at once, dispatched concurrently --
    see list_registry_index's docstring for why this matters for page-load
    latency. Returns {pack_name: latest_json_or_None}."""
    results = _io_pool.map(get_latest, pack_names)
    return dict(zip(pack_names, results))


def get_latest(pack_name: str, project_id: str | None = None) -> dict | None:
    try:
        obj = _s3.get_object(Bucket=settings.registry_bucket, Key=f"{_prefix(project_id)}{pack_name}/latest.json")
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        raise
    return json.loads(obj["Body"].read())


def get_version_metadata(pack_name: str, version: str) -> dict | None:
    try:
        obj = _s3.get_object(Bucket=settings.registry_bucket, Key=f"packs/{pack_name}/{version}/version.json")
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        raise
    return json.loads(obj["Body"].read())


def list_versions(pack_name: str) -> list[str]:
    paginator = _s3.get_paginator("list_objects_v2")
    versions: list[str] = []
    for page in paginator.paginate(Bucket=settings.registry_bucket, Prefix=f"packs/{pack_name}/", Delimiter="/"):
        for prefix in page.get("CommonPrefixes", []):
            # prefix["Prefix"] looks like "packs/python/1.0.0/"
            versions.append(prefix["Prefix"].rstrip("/").split("/")[-1])
    return sorted(versions)


def get_content_zip(
    pack_name: str, version: str, content_type: ContentType, project_id: str | None = None
) -> bytes | None:
    """Returns None if this pack/version has no content of this type -- the
    expected, common case (e.g. "core" has no standards.zip at all), not an
    error. Route handlers turn None into a 404."""
    try:
        obj = _s3.get_object(
            Bucket=settings.registry_bucket, Key=f"{_prefix(project_id)}{pack_name}/{version}/{content_type}.zip"
        )
    except ClientError as exc:
        if exc.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        raise
    return obj["Body"].read()


def available_content_types(pack_name: str, version: str) -> list[ContentType]:
    """Which of standards/skills/agents actually exist for this pack/version --
    used to decide which tabs to show on the pack detail screen, by probing
    each object's existence rather than trusting version.json's content_types
    field (which can go stale after a partial re-publish; see
    scripts/publish_pack.py)."""
    present = []
    for content_type in CONTENT_TYPES:
        try:
            _s3.head_object(Bucket=settings.registry_bucket, Key=f"packs/{pack_name}/{version}/{content_type}.zip")
            present.append(content_type)
        except ClientError as exc:
            if exc.response["Error"]["Code"] not in ("NoSuchKey", "404"):
                raise
    return present


def list_files_in_zip(zip_bytes: bytes) -> dict[str, str]:
    """Returns {filename: text_content} for every file in a flat archive
    (standards or agents), for rendering on the pack detail screen."""
    files: dict[str, str] = {}
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        for info in sorted(zf.infolist(), key=lambda i: i.filename):
            if info.is_dir():
                continue
            files[info.filename] = zf.read(info).decode("utf-8", errors="replace")
    return files


def build_zip_from_files(files: dict[str, str]) -> bytes:
    """Inverse of list_files_in_zip/list_skills_in_zip combined -- given
    {path: content} (path is a flat filename for standards/agents, or
    "<skill-name>/<filename>" for skills), produces a zip archive. The caller
    doesn't need to branch on content_type: a flat key just creates a
    top-level entry, a key with "/" creates the nested nested structure.
    """
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, content in files.items():
            zf.writestr(path, content)
    return buf.getvalue()


def put_content_zip(
    pack_name: str, version: str, content_type: ContentType, zip_bytes: bytes, project_id: str | None = None
) -> None:
    _s3.put_object(
        Bucket=settings.registry_bucket,
        Key=f"{_prefix(project_id)}{pack_name}/{version}/{content_type}.zip",
        Body=zip_bytes,
        ContentType="application/zip",
    )


def put_version_metadata(pack_name: str, version: str, metadata: dict) -> None:
    _s3.put_object(
        Bucket=settings.registry_bucket,
        Key=f"packs/{pack_name}/{version}/version.json",
        Body=json.dumps(metadata, indent=2).encode("utf-8"),
        ContentType="application/json",
    )


def put_latest(pack_name: str, version: str, project_id: str | None = None) -> None:
    _s3.put_object(
        Bucket=settings.registry_bucket,
        Key=f"{_prefix(project_id)}{pack_name}/latest.json",
        Body=json.dumps({"pack": pack_name, "version": version}, indent=2).encode("utf-8"),
        ContentType="application/json",
    )


def project_has_fork(pack_name: str, project_id: str) -> bool:
    return bool(get_latest(pack_name, project_id=project_id))


def fork_pack_for_project(pack_name: str, project_id: str) -> dict:
    """Copies the pack's current global baseline content into a project-owned
    namespace ("projects/<project_id>/packs/<pack_name>/..."), so that
    project's future fetches (see main.py's api_pack_content) and pushes
    (see the fork content-type route) target this copy instead of the shared
    baseline. One-time: callers must check project_has_fork first and 409 if
    a fork already exists, since re-running this would silently discard
    anything already pushed to the fork.

    Raises ValueError if the pack has no published baseline at all -- callers
    turn that into a 404, there's nothing to copy."""
    latest = get_latest(pack_name)
    if not latest:
        raise ValueError(f"pack '{pack_name}' has no published version to fork")

    for content_type in CONTENT_TYPES:
        zip_bytes = get_content_zip(pack_name, latest["version"], content_type)
        if zip_bytes is not None:
            put_content_zip(pack_name, FORK_VERSION, content_type, zip_bytes, project_id=project_id)

    put_latest(pack_name, FORK_VERSION, project_id=project_id)
    return {"pack": pack_name, "version": FORK_VERSION, "forked_from": latest["version"]}


def list_skills_in_zip(zip_bytes: bytes) -> dict[str, dict[str, str]]:
    """Returns {skill_name: {filename: text_content}} for a skills archive,
    which preserves one level of <skill-name>/ nesting (usually just
    SKILL.md per skill, but render whatever's actually there)."""
    skills: dict[str, dict[str, str]] = {}
    with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
        for info in sorted(zf.infolist(), key=lambda i: i.filename):
            if info.is_dir():
                continue
            parts = info.filename.split("/")
            if len(parts) < 2:
                continue
            skill_name, filename = parts[-2], parts[-1]
            skills.setdefault(skill_name, {})[filename] = zf.read(info).decode("utf-8", errors="replace")
    return skills
