#!/usr/bin/env python3
"""Admin-only: publish a pack version (standards/skills/agents) to the
Standards Registry (S3).

Not a product feature -- see docs/phases/sr-1-registry-infrastructure.md
("Admin publish script"). Exists only so a human with registry write access can:
  - migrate the bundled packs to their current version as a one-time task
  - produce test fixtures for CLI registry-fetch tests
  - publish a version before SR.3's real authenticated web app publish flow exists

Requires AWS credentials with write access to the registry bucket, resolved via
boto3's default credential chain (environment, profile, or IRSA if run in-cluster).

Each of --standards-source/--skills-source/--agents-source is independently
optional -- a pack like "core" has only skills+agents (no standards_packs/core
directory); a pack like "angular" may have standards+skills but no
stack-specific agents. At least one must be given.

--skills-source expects a directory of *.md files, one per skill (same layout
as cli/src/cartographer/skills_packs/<name>/) -- each file's stem becomes a
<skill-name>/ subdirectory containing SKILL.md in the archive, matching the
structure cartographer/standards_registry.py's extract_skills_zip expects.
--standards-source and --agents-source are zipped flat (same as before).

Usage:
    python scripts/publish_pack.py \\
        --bucket my-standards-registry \\
        --pack python \\
        --version 1.0.0 \\
        --standards-source cli/src/cartographer/standards_packs/python \\
        --skills-source cli/src/cartographer/skills_packs/python \\
        --agents-source cli/src/cartographer/agents_packs/python \\
        --changelog "Initial migration from bundled CLI pack" \\
        --published-by you@example.com
"""

from __future__ import annotations

import argparse
import datetime
import io
import json
import sys
import zipfile
from pathlib import Path


def build_flat_zip(source_dir: Path) -> bytes:
    """Zip every .md file in source_dir, flat. Used for standards and agents."""
    md_files = sorted(source_dir.glob("*.md"))
    if not md_files:
        raise SystemExit(f"no .md files found in {source_dir}")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in md_files:
            zf.write(f, arcname=f.name)
    return buf.getvalue()


def build_skills_zip(source_dir: Path) -> bytes:
    """Zip every *.md file in source_dir as <stem>/SKILL.md -- matches the
    layout cartographer's bundled skills_packs/<name>/ directories use
    (one flat .md file per skill) and what extract_skills_zip expects on
    the CLI side (one subdirectory per skill)."""
    md_files = sorted(source_dir.glob("*.md"))
    if not md_files:
        raise SystemExit(f"no .md files found in {source_dir}")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for f in md_files:
            zf.write(f, arcname=f"{f.stem}/SKILL.md")
    return buf.getvalue()


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--bucket", required=True, help="S3 bucket name for the Standards Registry")
    parser.add_argument("--pack", required=True, help="Pack name, e.g. python or core")
    parser.add_argument("--version", required=True, help="Semver version being published, e.g. 1.0.0")
    parser.add_argument("--standards-source", type=Path, default=None, help="Directory of standards .md files (optional)")
    parser.add_argument("--skills-source", type=Path, default=None, help="Directory of skill .md files, one per skill (optional)")
    parser.add_argument("--agents-source", type=Path, default=None, help="Directory of agent .md files (optional)")
    parser.add_argument("--changelog", required=True, help="Changelog text for this version")
    parser.add_argument("--published-by", required=True, help="Email or identifier of the publisher")
    args = parser.parse_args()

    if not any([args.standards_source, args.skills_source, args.agents_source]):
        raise SystemExit("at least one of --standards-source/--skills-source/--agents-source is required")

    try:
        import boto3
    except ImportError:
        sys.exit("boto3 is required: pip install boto3")

    s3 = boto3.client("s3")

    content_types_published = []
    if args.standards_source:
        zip_bytes = build_flat_zip(args.standards_source)
        key = f"packs/{args.pack}/{args.version}/standards.zip"
        s3.put_object(Bucket=args.bucket, Key=key, Body=zip_bytes, ContentType="application/zip")
        content_types_published.append("standards")
        print(f"published {args.pack} v{args.version} standards -> s3://{args.bucket}/{key}")

    if args.skills_source:
        zip_bytes = build_skills_zip(args.skills_source)
        key = f"packs/{args.pack}/{args.version}/skills.zip"
        s3.put_object(Bucket=args.bucket, Key=key, Body=zip_bytes, ContentType="application/zip")
        content_types_published.append("skills")
        print(f"published {args.pack} v{args.version} skills -> s3://{args.bucket}/{key}")

    if args.agents_source:
        zip_bytes = build_flat_zip(args.agents_source)
        key = f"packs/{args.pack}/{args.version}/agents.zip"
        s3.put_object(Bucket=args.bucket, Key=key, Body=zip_bytes, ContentType="application/zip")
        content_types_published.append("agents")
        print(f"published {args.pack} v{args.version} agents -> s3://{args.bucket}/{key}")

    version_obj = {
        "pack": args.pack,
        "version": args.version,
        "published_at": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "published_by": args.published_by,
        "changelog": args.changelog,
        "content_types": content_types_published,
    }
    version_key = f"packs/{args.pack}/{args.version}/version.json"
    s3.put_object(
        Bucket=args.bucket,
        Key=version_key,
        Body=json.dumps(version_obj, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    latest_key = f"packs/{args.pack}/latest.json"
    latest_obj = {"pack": args.pack, "version": args.version}
    s3.put_object(
        Bucket=args.bucket,
        Key=latest_key,
        Body=json.dumps(latest_obj, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    print(f"updated   {args.pack}/latest.json -> version {args.version}")


if __name__ == "__main__":
    main()
