# Standards Registry Pass SR.1: Registry Infrastructure

## Goal

A pack version published into S3 by hand (via a throwaway admin script, no web app required yet) exists as an immutable, versioned object with a well-defined schema -- proving the storage layer and schema before anything is built to read or write it over a network.

**Renamed and rescoped 2026-10-05** (was "sr-1-registry-and-cli-fetch.md", included CLI registry fetch). Corrected after review: the original design had the CLI fetch pack content directly from a public-read S3 bucket via CloudFront, with no request-level authentication -- anyone with a pack's URL could read it, and there was no way to audit or restrict access. Fixed by making S3 private and routing all reads through the web app's own authenticated API instead (see `ARCHITECTURE.md` §7.2's correction note). That means CLI fetch now depends on the web app's API existing, not just S3 -- it moved to [sr-2-webapp-auth-and-read-views.md](sr-2-webapp-auth-and-read-views.md), merged with that phase's web app work. This phase (SR.1) is now storage-only: no CLI changes, no `stacks.registry_url`/`registry_fallback` config wiring, no network-reachable fetch path at all. Those all live in SR.2 now.

**Entry condition:** OQ-08, OQ-09, OQ-10 resolved (done, see [OPEN_QUESTIONS.md](../OPEN_QUESTIONS.md) closed questions). No dependency on any other sub-phase.

**Status: complete as of 2026-10-05.** Provisioned `s3://cartographer-standards-registry-983883745126` (account `983883745126`, `us-east-1`), versioned, all public access blocked. Ran `scripts/publish_pack.py` for all 12 bundled packs at `1.0.0`, using the changelog "Initial migration from bundled CLI pack (cartographer v0.1.0)". All three exit criteria verified against the live bucket, not mocked:
1. `aws s3api list-objects-v2` confirms exactly 36 objects (12 packs × `standards.zip`/`version.json`/`latest.json`), correct keys.
2. An unauthenticated `curl` against a real object's URL returns `403 AccessDenied`.
3. Re-running the admin script for `python`/`1.0.0` produced a byte-identical `standards.zip` (same ETag `05fb5f9e8676756b26fae0c031e0f602`) -- idempotent, no corruption. (The bucket's versioning correctly recorded this as a second object version, since it's a new PUT -- "idempotent" here means consistent content, not that S3 skips the write.)

**Bucket name for SR.2 onward:** `cartographer-standards-registry-983883745126`, region `us-east-1`. The web app's IRSA role (SR.2) needs read access to it; the admin script retains direct IAM write access for any future manual republish.

---

## Scope

### In scope

| Component | What ships |
|---|---|
| S3 bucket (private) | Versioned bucket, no public access of any kind. Write restricted to IAM; read restricted to IAM (the web app's IRSA role, added in SR.2, and the admin script below). |
| Pack version object schema | A pack version is an immutable zip archive (all of the pack's `.md` files, flat) plus a small JSON metadata object. Documented below. |
| Admin publish script | `scripts/publish_pack.py` -- uploads a pack version to S3 by hand, using the admin's own IAM credentials (not the app's). Not a product feature -- exists only so this phase and the bundled-pack migration can be tested without waiting on the web app's authenticated write path (SR.3). |
| Bundled pack migration | All 12 current bundled packs (`cross-stack`, `python`, `react`, `typescript`, `golang`, `rust`, `java`, `kotlin`, `angular`, `vue`, `swift`, `dart` -- see `components/standards-packs.md`) published as their current version using the admin script |

### Explicitly out of scope (moved to SR.2, or deferred further)

- Any network-reachable read path -- nothing in this phase is fetchable by the CLI or by anything outside an operator running the admin script with their own AWS credentials
- `stacks.registry_url`/`registry_fallback` config fields and CLI wiring -- SR.2
- The web app itself -- SR.2, SR.3, SR.4
- Any authenticated publish path -- publishing in this phase is an admin running a script with IAM credentials, not a product flow (SR.3 adds the real one)
- Draft/review workflow -- there is no draft state yet, only already-decided versions being uploaded directly

---

## Component breakdown

### 1. S3 infrastructure

- S3 bucket with versioning enabled (OQ-08 decision: S3, with the object layout below kept S3-compatible so R2/MinIO can substitute later without a schema change)
- **No public access, no CloudFront.** Bucket policy denies all public access; only the IAM principal running the admin script (this phase) and, starting in SR.2, the web app's IRSA role can read or write.
- Object key structure: `packs/<pack-name>/<version>/standards.zip` (the archive) and `packs/<pack-name>/<version>/version.json` (metadata)
- Index object per pack: `packs/<pack-name>/latest.json`

### 2. Pack version object schema

A pack version is a **zip archive** containing all of the pack's `.md` files, flat (no subdirectories) -- not a single `standards.md` as an earlier draft of this doc assumed. Every one of the 12 bundled packs ships multiple files (`cross-stack` alone has 28; see `components/standards-packs.md` and `README.md`'s per-pack file counts), so a single-file schema didn't match any real pack. Corrected during implementation; see `cartographer/standards_registry.py`'s module docstring for the client-side half of this.

`packs/<pack-name>/<version>/version.json`:

```json
{
  "pack":         "python",
  "version":      "2.2.0",
  "published_at": "2026-09-24T10:00:00Z",
  "published_by": "a.patel@example.com",
  "changelog":    "Added async section; updated testing conventions."
}
```

`packs/<pack-name>/latest.json`:

```json
{
  "pack":    "python",
  "version": "2.2.0"
}
```

Note what's *not* here anymore: no `content_url`/`url` field pointing at a public S3/CDN location. The archive's location is an implementation detail of the web app's backend (SR.2) -- nothing outside the app ever constructs an S3 URL directly.

### 3. Admin publish script

`scripts/publish_pack.py` -- given a pack name, version, changelog, and a local directory of `.md` files, zips them and uploads the archive plus `version.json`/`latest.json` to S3 using the operator's own AWS credentials (boto3 default credential chain). Used for:
- The one-time migration of the 12 bundled packs to their current version
- Producing test fixtures for SR.2's registry-read API tests
- Any publish needed before SR.3 ships the real authenticated publish flow

This script is throwaway once SR.3 ships -- it is not part of the product and should not grow features. It bypasses the web app entirely (direct S3 access), which is fine for an operator with legitimate infrastructure credentials; it is not a precedent for any other reads or writes bypassing the app.

---

## Build order

```
1. Provision S3 bucket (private, versioned) -- or a local equivalent for dev/test (see Test approach)
2. Define and document the pack version object schema (this file is the spec; no separate schema doc needed at this size)
3. Write the admin publish script
4. Migrate the 12 bundled packs: run the admin script once per pack at their current version
```

---

## Exit criteria

| # | Criterion | How to verify |
|---|---|---|
| 1 | All 12 bundled packs have a published version in S3 with correct key structure (`standards.zip` + `version.json` + `latest.json`) | Inspect the bucket directly |
| 2 | The bucket has no public access of any kind | Attempt an unauthenticated HTTP GET against any object URL; confirm it is denied |
| 3 | The admin script is idempotent for a re-publish of the same version (no corruption, consistent content) | Run it twice for the same pack/version; confirm the resulting objects are identical |

Nothing in this phase is CLI- or web-app-reachable yet -- that's the point. SR.2's exit criteria are where "the CLI can fetch a pack" first becomes verifiable.

---

## Test approach

**Unit tests:**
- Admin script: zip construction includes all `.md` files in a source directory, flat, and rejects a source directory with no `.md` files.

**Integration tests:**
- Admin script against a real (or LocalStack) S3 bucket: run it, then inspect the bucket directly via `boto3` to confirm `standards.zip`, `version.json`, and `latest.json` all exist with correct content and keys.

No CLI or web app tests in this phase -- there is nothing for them to call yet.

---

*Next: [sr-2-webapp-auth-and-read-views.md](sr-2-webapp-auth-and-read-views.md) builds the web app's auth, the authenticated registry-read API, and CLI registry fetch against it -- the first phase where any of this is reachable outside an operator's own AWS credentials.*
