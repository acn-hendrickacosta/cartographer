"""Publish an APPROVED draft: reassemble the pack's content-type archive
(every file from the current published version, with the draft's file
replacing or adding to it) and write it to S3 as a new version.

This is the first place the web app itself writes to S3 -- SR.1 used an
admin script, SR.2 was read-only.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app import s3_registry


def publish_draft(draft: dict) -> None:
    """Writes the new version's <content_type>.zip + version.json to S3 and
    updates latest.json. Does not touch the draft's own state -- the caller
    (app/main.py's publish route) transitions it to PUBLISHED separately,
    after this succeeds, so a storage failure doesn't leave the draft
    claiming to be published when it isn't."""
    pack_name = draft["pack_name"]
    content_type = draft["content_type"]
    version = draft["target_version"]

    files: dict[str, str] = {}
    latest = s3_registry.get_latest(pack_name)
    if latest:
        existing_zip = s3_registry.get_content_zip(pack_name, latest["version"], content_type)
        if existing_zip:
            if content_type == "skills":
                skills = s3_registry.list_skills_in_zip(existing_zip)
                files = {f"{skill}/{fname}": content for skill, fs in skills.items() for fname, content in fs.items()}
            else:
                files = s3_registry.list_files_in_zip(existing_zip)

    files[draft["file_name"]] = draft["content"]

    zip_bytes = s3_registry.build_zip_from_files(files)
    s3_registry.put_content_zip(pack_name, version, content_type, zip_bytes)
    s3_registry.put_version_metadata(
        pack_name,
        version,
        {
            "pack": pack_name,
            "version": version,
            "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "published_by": draft["author_email"],
            "changelog": f"Updated {draft['file_name']} via web app authoring/review",
        },
    )
    s3_registry.put_latest(pack_name, version)
