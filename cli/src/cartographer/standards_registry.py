"""Standards Registry client: fetch published pack versions via the web app's
authenticated API.

See docs/phases/sr-2-webapp-auth-and-read-views.md. **Corrected 2026-10-05**
(this module originally fetched directly from a public S3/CloudFront URL, no
auth at all -- flagged during review as a real access-control gap). The CLI
now calls `GET {registry_url}/api/packs/<name>/content/<content_type>` with a
per-project bearer token (`cartographer.local.toml`'s `registry_token`, or
`CARTO_REGISTRY_TOKEN`). The web app validates the token server-side, reads
the pack from its private S3 bucket, and returns the zip archive directly --
the CLI never constructs or touches an S3 URL.

**Extended 2026-10-05** to cover all three content types `apply_pack` installs
-- standards, skills, and agents -- not just standards. Each is independently
optional per pack (e.g. "angular" has no stack-specific agents; "core" has no
standards at all). Skills archives preserve one level of subdirectory nesting
(`<skill-name>/SKILL.md`) since that's the structure Claude Code requires to
auto-load them; standards and agents archives are flat, same as before.

**Extended again (SR.5)** with per-project forks: `fork_pack` (POST .../fork)
and `push_fork_content` (PUT .../fork/<content_type>) let a project copy a
pack's baseline into its own namespace in the registry and push local edits
back to it, using the same bearer token as fetch_pack_content. See
commands/stack.py's `fork`/`push` commands and docs/phases/sr-5-project-forks.md.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Literal

ContentType = Literal["standards", "skills", "agents"]


class RegistryFetchError(Exception):
    """Raised on any registry fetch failure: missing/invalid token, network,
    HTTP, or malformed response.

    Callers (commands/stack.py) catch this to implement stacks.registry_fallback
    ("warn": log and use the bundled version; "error": exit 1).
    """


class RegistryContentNotFoundError(RegistryFetchError):
    """Raised specifically on a 404 -- this pack genuinely has no published
    content of this type (e.g. 'angular' has no stack-specific agents at all).
    Distinguished from other failures because it's the overwhelmingly common,
    expected case once skills/agents are in scope (every pack x content_type
    pair is attempted, and most packs don't have all three types) -- callers
    treat this as a silent fallback regardless of stacks.registry_fallback,
    while a real failure (bad token, network, 5xx) still respects it."""


class RegistryForkConflictError(RegistryFetchError):
    """Raised on a 409 -- this project already has a fork of this pack.
    Forking again would silently discard whatever was already pushed to it,
    so the server refuses rather than re-copying; see fork_pack."""


def fetch_pack_content(
    registry_url: str, pack_name: str, content_type: ContentType, token: str, timeout: float = 10.0
) -> tuple[str, bytes]:
    """Fetch the latest published version of one content type for a pack.

    Calls GET {registry_url}/api/packs/{pack_name}/content/{content_type}
    with the given bearer token. Returns (version, zip_bytes) -- version
    comes from the response's X-Pack-Version header. Raises
    RegistryFetchError on any failure, including a missing/empty token
    (checked client-side so a misconfigured project fails fast with a clear
    message instead of always getting a 401 from the server).
    """
    if not token:
        raise RegistryFetchError(
            "registry_url is configured but no registry_token is set "
            "(cartographer.local.toml or CARTO_REGISTRY_TOKEN)"
        )

    url = f"{registry_url.rstrip('/')}/api/packs/{pack_name}/content/{content_type}"
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})

    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310 - registry_url is operator-configured, not user input
            zip_bytes = resp.read()
            version = resp.headers.get("X-Pack-Version", "")
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise RegistryFetchError(f"registry rejected the configured token (401) for '{pack_name}'") from exc
        if exc.code == 404:
            raise RegistryContentNotFoundError(
                f"pack '{pack_name}' has no published {content_type} in the registry (404)"
            ) from exc
        raise RegistryFetchError(f"registry returned HTTP {exc.code} for '{pack_name}': {exc}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RegistryFetchError(f"could not reach {url}: {exc}") from exc

    if not version:
        raise RegistryFetchError(f"registry response for '{pack_name}' is missing the X-Pack-Version header")

    return version, zip_bytes


def fork_pack(registry_url: str, pack_name: str, token: str, timeout: float = 10.0) -> dict:
    """POST {registry_url}/api/packs/{pack_name}/fork -- copies the pack's
    current baseline into this project's own namespace in the registry.
    One-time: raises RegistryForkConflictError if already forked, or
    RegistryContentNotFoundError if the pack has no published baseline yet.
    """
    if not token:
        raise RegistryFetchError(
            "registry_url is configured but no registry_token is set "
            "(cartographer.local.toml or CARTO_REGISTRY_TOKEN)"
        )

    url = f"{registry_url.rstrip('/')}/api/packs/{pack_name}/fork"
    request = urllib.request.Request(url, method="POST", headers={"Authorization": f"Bearer {token}"})

    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310 - registry_url is operator-configured, not user input
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 409:
            raise RegistryForkConflictError(f"project already has a fork of '{pack_name}'") from exc
        if exc.code == 404:
            raise RegistryContentNotFoundError(f"pack '{pack_name}' has no published version to fork") from exc
        raise RegistryFetchError(f"registry returned HTTP {exc.code} forking '{pack_name}': {exc}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RegistryFetchError(f"could not reach {url}: {exc}") from exc


def push_fork_content(
    registry_url: str, pack_name: str, content_type: ContentType, zip_bytes: bytes, token: str, timeout: float = 10.0
) -> None:
    """PUT {registry_url}/api/packs/{pack_name}/fork/{content_type} -- pushes
    this project's current local content for one content type, wholesale
    replacing whatever was previously in the fork. Raises
    RegistryContentNotFoundError if no fork exists yet (caller should tell
    the user to run `cartographer stack fork <pack>` first)."""
    if not token:
        raise RegistryFetchError(
            "registry_url is configured but no registry_token is set "
            "(cartographer.local.toml or CARTO_REGISTRY_TOKEN)"
        )

    url = f"{registry_url.rstrip('/')}/api/packs/{pack_name}/fork/{content_type}"
    request = urllib.request.Request(url, data=zip_bytes, method="PUT", headers={"Authorization": f"Bearer {token}"})

    try:
        with urllib.request.urlopen(request, timeout=timeout):  # noqa: S310 - registry_url is operator-configured, not user input
            pass
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RegistryContentNotFoundError(
                f"project has no fork of '{pack_name}' yet -- run 'cartographer stack fork {pack_name}' first"
            ) from exc
        raise RegistryFetchError(
            f"registry returned HTTP {exc.code} pushing '{pack_name}' {content_type}: {exc}"
        ) from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise RegistryFetchError(f"could not reach {url}: {exc}") from exc


def build_flat_zip(dir_path: Path, filenames: list[str]) -> bytes:
    """Zip exactly these files from dir_path, flat (arcname = filename) --
    used to push standards/agents content. Mirrors scripts/publish_pack.py's
    build_flat_zip, but from an explicit file list (the provenance manifest,
    see commands/stack.py) rather than globbing the whole directory, since
    agents live in a directory shared with other installed packs."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for filename in filenames:
            zf.writestr(filename, (dir_path / filename).read_text(encoding="utf-8"))
    return buf.getvalue()


def build_skills_zip(skills_root: Path, skill_names: list[str]) -> bytes:
    """Zip exactly these skills' SKILL.md files from skills_root, preserving
    the <skill-name>/ nesting extract_skills_zip expects on the way back in."""
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for skill_name in skill_names:
            zf.writestr(f"{skill_name}/SKILL.md", (skills_root / skill_name / "SKILL.md").read_text(encoding="utf-8"))
    return buf.getvalue()


def extract_pack_zip(zip_bytes: bytes, dest_dir: Path) -> list[Path]:
    """Extract a flat archive (standards or agents) into dest_dir.

    Always overwrites -- fetched content is the authoritative newer version;
    unlike the bundled path there's no meaningful content-equality check to
    skip a write.

    Only each entry's basename is ever used as the destination filename, which
    makes path traversal via a crafted archive (`../../etc/passwd`) structurally
    impossible rather than something that needs separate validation.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                name = Path(info.filename).name
                if not name:
                    continue
                dest_file = dest_dir / name
                dest_file.write_bytes(zf.read(info))
                written.append(dest_file)
    except zipfile.BadZipFile as exc:
        raise RegistryFetchError(f"pack archive is not a valid zip: {exc}") from exc
    return written


def extract_skills_zip(zip_bytes: bytes, skills_root: Path) -> list[Path]:
    """Extract a skills archive into skills_root, preserving exactly one level
    of subdirectory nesting (<skill-name>/SKILL.md) -- the structure Claude
    Code requires to auto-load a skill and expose it as a /<name> command.

    Only the last two path components of each entry are ever used
    (skill-name/filename), which makes path traversal structurally
    impossible the same way extract_pack_zip's basename-only approach does.
    """
    skills_root.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    try:
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            for info in zf.infolist():
                if info.is_dir():
                    continue
                parts = Path(info.filename).parts
                if len(parts) < 2:
                    continue  # not in a <skill-name>/ subdirectory -- skip, matches no valid skill layout
                skill_name, filename = parts[-2], parts[-1]
                if not skill_name or not filename:
                    continue
                dest_file = skills_root / skill_name / filename
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                dest_file.write_bytes(zf.read(info))
                written.append(dest_file)
    except zipfile.BadZipFile as exc:
        raise RegistryFetchError(f"skills archive is not a valid zip: {exc}") from exc
    return written
