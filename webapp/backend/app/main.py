"""Standards web app backend (SR.2 slice): a JSON API consumed by the React
SPA (webapp/frontend/, built into app/static/dist/ -- see frontend/README or
the root webapp/README.md), plus the CLI's authenticated content endpoint.
No draft/review/publish yet (SR.3) and no admin screens yet (SR.4).

**Rebuilt 2026-10-05** from server-rendered Jinja2 pages to this JSON API +
static SPA. The Jinja2 version caused a full page reload on every navigation
click -- correctly flagged as slow -- and nested standards/skills/agents as
in-page tabs rather than top-level sidebar destinations, inconsistent with
cartographer ui's own Explore/Registry/Stats sidebar pattern. Session-cookie
auth (Cognito hosted UI redirect flow) is unchanged; the SPA calls GET /api/me
to learn whether it's logged in, since it can't inspect the httponly cookie
directly.
"""

from __future__ import annotations

import secrets
from pathlib import Path

import jwt
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.middleware.sessions import SessionMiddleware

from app import auth, cognito_admin, drafts, packs_admin, publish, s3_registry, tokens
from app.settings import settings

app = FastAPI(title="Cartographer Standards Registry")
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret, same_site="lax")

STATIC_DIR = Path(__file__).parent / "static"
DIST_DIR = STATIC_DIR / "dist"


def _require_session(request: Request) -> auth.SessionUser:
    return auth.current_user(request)  # raises HTTPException(401) if not logged in


def _require_role(request: Request, role: str) -> auth.SessionUser:
    user = _require_session(request)
    if role not in user.groups:
        raise HTTPException(status_code=403, detail=f"requires the {role} role")
    return user


def _version_tuple(version: str) -> tuple[int, ...]:
    """Best-effort numeric comparison for simple semver like '1.2.0'. Falls
    back to treating the whole string as one component if it doesn't parse,
    so an odd version string fails the "must be higher" check loudly rather
    than crashing."""
    try:
        return tuple(int(part) for part in version.split("."))
    except ValueError:
        return (0,)


# ---------------------------------------------------------------------------
# Auth (redirect-based, Cognito Hosted UI -- not meaningfully convertible to
# a pure JSON API; the SPA triggers these via window.location, not fetch)
# ---------------------------------------------------------------------------

@app.get("/login")
def login():
    state = secrets.token_urlsafe(16)
    return RedirectResponse(url=auth.hosted_ui_login_url(state=state))


@app.get("/auth/callback")
async def auth_callback(request: Request, code: str | None = None, error: str | None = None):
    if error or not code:
        raise HTTPException(status_code=401, detail=f"login failed: {error or 'no code returned'}")
    tokens_resp = await auth.exchange_code_for_tokens(code)
    try:
        user = auth.verify_id_token(tokens_resp["id_token"])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail=f"id token verification failed: {exc}") from exc
    request.session["user"] = user.to_session_dict()
    return RedirectResponse(url="/")


@app.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url=auth.hosted_ui_logout_url())


# ---------------------------------------------------------------------------
# JSON API (consumed by the React SPA)
# ---------------------------------------------------------------------------

@app.get("/api/me")
def api_me(request: Request):
    user = _require_session(request)
    return {"email": user.email, "groups": user.groups}


@app.get("/api/packs")
def api_packs(request: Request, type: s3_registry.ContentType):  # noqa: A002 - "type" matches the query param name intentionally
    """List packs that have published content of the given type, with their
    latest version. One sidebar view (Standards/Skills/Agents) = one call
    with a different `type`.

    One bulk LIST (list_registry_index) plus concurrent latest.json GETs
    (get_latest_many), not a per-pack GET+3xHEAD loop -- that sequential
    version was the actual cause of "everything loads super slow": up to 52
    blocking S3 round-trips for a single page load. See
    list_registry_index's docstring."""
    _require_session(request)
    index = s3_registry.list_registry_index()
    latest_by_pack = s3_registry.get_latest_many(list(index.keys()))

    packs = []
    for name, latest in latest_by_pack.items():
        if not latest:
            continue
        available = index.get(name, {}).get(latest["version"], set())
        if type in available:
            packs.append({"name": name, "version": latest["version"]})
    packs.sort(key=lambda p: p["name"])
    return packs


@app.get("/api/packs/{name}/{content_type}")
def api_pack_detail(request: Request, name: str, content_type: s3_registry.ContentType):
    """Pack detail for one content type: metadata + files. Skills archives
    are flattened to {"<skill-name>/SKILL.md": content} keys so the response
    shape is identical across all three content types -- the frontend doesn't
    need type-specific parsing, just renders whatever keys come back."""
    _require_session(request)

    latest = s3_registry.get_latest(name)
    if not latest:
        raise HTTPException(status_code=404, detail=f"pack '{name}' has no published version")

    zip_bytes = s3_registry.get_content_zip(name, latest["version"], content_type)
    if not zip_bytes:
        raise HTTPException(
            status_code=404, detail=f"pack '{name}' has no published {content_type}"
        )

    if content_type == "skills":
        skills = s3_registry.list_skills_in_zip(zip_bytes)
        files = {f"{skill}/{fname}": content for skill, fs in skills.items() for fname, content in fs.items()}
    else:
        files = s3_registry.list_files_in_zip(zip_bytes)

    metadata = s3_registry.get_version_metadata(name, latest["version"])
    return {"name": name, "version": latest["version"], "metadata": metadata, "files": files}


@app.get("/api/packs/{name}/{content_type}/versions")
def api_pack_versions(request: Request, name: str, content_type: s3_registry.ContentType):
    _require_session(request)
    versions = []
    for version in s3_registry.list_versions(name):
        if content_type not in s3_registry.available_content_types(name, version):
            continue
        metadata = s3_registry.get_version_metadata(name, version)
        versions.append({"version": version, "metadata": metadata})
    versions.sort(key=lambda v: v["version"], reverse=True)
    return versions


# ---------------------------------------------------------------------------
# SR.3: drafts, review, publish. "Draft/review state" lives in Postgres
# (app/drafts.py); PUBLISHED is never written there -- S3 is the immutable
# source of truth for published content, same as before SR.3 existed.
# ---------------------------------------------------------------------------

class DraftCreate(BaseModel):
    pack_name: str
    content_type: s3_registry.ContentType
    file_name: str
    target_version: str
    content: str


class DraftUpdate(BaseModel):
    content: str
    target_version: str


class CommentCreate(BaseModel):
    body: str


class RejectBody(BaseModel):
    comment: str


@app.post("/api/drafts")
def api_create_draft(request: Request, body: DraftCreate):
    user = _require_role(request, "Author")
    if packs_admin.is_deprecated(body.pack_name):
        raise HTTPException(status_code=409, detail=f"pack '{body.pack_name}' is deprecated, cannot start new drafts")
    return drafts.create_draft(
        body.pack_name, body.content_type, body.file_name, body.target_version, user.email, body.content
    )


@app.get("/api/drafts/{draft_id}")
def api_get_draft(request: Request, draft_id: str):
    _require_session(request)
    draft = drafts.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft not found")
    return draft


@app.patch("/api/drafts/{draft_id}")
def api_update_draft(request: Request, draft_id: str, body: DraftUpdate):
    user = _require_session(request)
    draft = drafts.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft not found")
    if draft["author_email"] != user.email:
        raise HTTPException(status_code=403, detail="only the draft's author can edit it")
    updated = drafts.update_draft(draft_id, body.content, body.target_version)
    if not updated:
        raise HTTPException(status_code=409, detail="draft is not in DRAFT state, cannot edit")
    return updated


@app.delete("/api/drafts/{draft_id}")
def api_discard_draft(request: Request, draft_id: str):
    user = _require_session(request)
    draft = drafts.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft not found")
    if draft["author_email"] != user.email:
        raise HTTPException(status_code=403, detail="only the draft's author can discard it")
    if not drafts.delete_draft(draft_id):
        raise HTTPException(status_code=409, detail="draft is not in DRAFT state, cannot discard")
    return {"ok": True}


@app.post("/api/drafts/{draft_id}/submit")
def api_submit_draft(request: Request, draft_id: str):
    user = _require_session(request)
    draft = drafts.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft not found")
    if draft["author_email"] != user.email:
        raise HTTPException(status_code=403, detail="only the draft's author can submit it")

    latest = s3_registry.get_latest(draft["pack_name"])
    if latest and _version_tuple(draft["target_version"]) <= _version_tuple(latest["version"]):
        raise HTTPException(
            status_code=400,
            detail=f"target_version {draft['target_version']} must be higher than the current published version {latest['version']}",
        )

    updated = drafts.transition(draft_id, ("DRAFT",), "IN_REVIEW")
    if not updated:
        raise HTTPException(status_code=409, detail="draft is not in DRAFT state, cannot submit")
    return updated


@app.post("/api/drafts/{draft_id}/revise")
def api_revise_draft(request: Request, draft_id: str):
    user = _require_session(request)
    draft = drafts.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft not found")
    if draft["author_email"] != user.email:
        raise HTTPException(status_code=403, detail="only the draft's author can revise it")
    updated = drafts.transition(draft_id, ("REJECTED",), "DRAFT")
    if not updated:
        raise HTTPException(status_code=409, detail="draft is not in REJECTED state, cannot revise")
    return updated


@app.get("/api/review-queue")
def api_review_queue(request: Request):
    _require_role(request, "Reviewer")
    return drafts.list_in_review()


@app.get("/api/drafts/{draft_id}/comments")
def api_list_comments(request: Request, draft_id: str):
    _require_session(request)
    if not drafts.get_draft(draft_id):
        raise HTTPException(status_code=404, detail="draft not found")
    return drafts.list_comments(draft_id)


@app.post("/api/drafts/{draft_id}/comments")
def api_add_comment(request: Request, draft_id: str, body: CommentCreate):
    user = _require_session(request)
    if not drafts.get_draft(draft_id):
        raise HTTPException(status_code=404, detail="draft not found")
    return drafts.add_comment(draft_id, user.email, body.body)


@app.post("/api/drafts/{draft_id}/approve")
def api_approve_draft(request: Request, draft_id: str):
    user = _require_role(request, "Reviewer")
    draft = drafts.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft not found")
    if draft["author_email"] == user.email:
        raise HTTPException(status_code=403, detail="a draft's own author cannot approve it")
    updated = drafts.transition(draft_id, ("IN_REVIEW",), "APPROVED")
    if not updated:
        raise HTTPException(status_code=409, detail="draft is not in IN_REVIEW state, cannot approve")
    return updated


@app.post("/api/drafts/{draft_id}/reject")
def api_reject_draft(request: Request, draft_id: str, body: RejectBody):
    user = _require_role(request, "Reviewer")
    draft = drafts.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft not found")
    if draft["author_email"] == user.email:
        raise HTTPException(status_code=403, detail="a draft's own author cannot reject it")
    if not body.comment.strip():
        raise HTTPException(status_code=400, detail="a rejection requires a comment")
    updated = drafts.transition(draft_id, ("IN_REVIEW",), "REJECTED")
    if not updated:
        raise HTTPException(status_code=409, detail="draft is not in IN_REVIEW state, cannot reject")
    drafts.add_comment(draft_id, user.email, body.comment)
    return updated


@app.post("/api/drafts/{draft_id}/publish")
def api_publish_draft(request: Request, draft_id: str):
    _require_role(request, "Reviewer")
    draft = drafts.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail="draft not found")
    if draft["state"] != "APPROVED":
        raise HTTPException(status_code=409, detail="draft is not in APPROVED state, cannot publish")

    publish.publish_draft(draft)  # writes to S3 first; only mark PUBLISHED if that succeeds

    updated = drafts.transition(draft_id, ("APPROVED",), "PUBLISHED")
    if not updated:
        # S3 write succeeded but the state flip raced with something else --
        # surfaced as a 500 rather than silently returning stale state, since
        # the registry and this record would otherwise disagree.
        raise HTTPException(status_code=500, detail="published to S3 but failed to update draft state")
    return updated


# ---------------------------------------------------------------------------
# SR.4: admin screens (user roles, pack management, registry tokens). All
# routes gated to the Admin role.
# ---------------------------------------------------------------------------

class RoleUpdate(BaseModel):
    groups: list[str]


class PackCreate(BaseModel):
    name: str


class TokenCreate(BaseModel):
    project_id: str


@app.get("/api/admin/users")
def api_admin_list_users(request: Request):
    _require_role(request, "Admin")
    return cognito_admin.list_users()


@app.patch("/api/admin/users/{email}")
def api_admin_set_user_groups(request: Request, email: str, body: RoleUpdate):
    _require_role(request, "Admin")
    try:
        return cognito_admin.set_user_groups(email, body.groups)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/admin/packs")
def api_admin_list_packs(request: Request):
    _require_role(request, "Admin")
    return packs_admin.list_packs()


@app.post("/api/admin/packs")
def api_admin_create_pack(request: Request, body: PackCreate):
    _require_role(request, "Admin")
    pack = packs_admin.create_pack(body.name)
    if not pack:
        raise HTTPException(status_code=409, detail=f"pack '{body.name}' already exists")
    return pack


@app.post("/api/admin/packs/{name}/deprecate")
def api_admin_deprecate_pack(request: Request, name: str):
    _require_role(request, "Admin")
    pack = packs_admin.deprecate_pack(name)
    if not pack:
        raise HTTPException(status_code=404, detail=f"pack '{name}' not found or already deprecated")
    return pack


@app.get("/api/admin/tokens")
def api_admin_list_tokens(request: Request):
    _require_role(request, "Admin")
    return tokens.list_tokens()


@app.post("/api/admin/tokens")
def api_admin_issue_token(request: Request, body: TokenCreate):
    _require_role(request, "Admin")
    return {"token": tokens.issue_token(body.project_id)}


@app.post("/api/admin/tokens/{token_hash}/revoke")
def api_admin_revoke_token(request: Request, token_hash: str):
    _require_role(request, "Admin")
    if not tokens.revoke_token(token_hash):
        raise HTTPException(status_code=404, detail="token not found or already revoked")
    return {"ok": True}


# ---------------------------------------------------------------------------
# CLI's authenticated content endpoint -- bearer-token auth, not session-cookie
# auth, since this is machine-to-machine. Also SR.5's per-project fork
# routes, same auth, since a fork is pushed/fetched by a project's own CLI,
# not a logged-in web app user.
# ---------------------------------------------------------------------------

def _require_bearer_project(request: Request) -> str:
    authorization = request.headers.get("Authorization", "")
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing Authorization: Bearer <token> header")
    token = authorization.removeprefix("Bearer ")

    project_id = tokens.validate_token(token)
    if not project_id:
        raise HTTPException(status_code=401, detail="invalid or revoked registry token")
    return project_id


@app.get("/api/packs/{name}/content/{content_type}")
def api_pack_content(request: Request, name: str, content_type: s3_registry.ContentType):
    project_id = _require_bearer_project(request)

    # SR.5: a project that has forked this pack gets served its own fork;
    # everyone else (the common case) gets the live global baseline exactly
    # as before -- this is what makes forking opt-in rather than something
    # that silently stops a project from receiving baseline updates.
    latest = s3_registry.get_latest(name, project_id=project_id)
    scope_project_id = project_id if latest else None
    if not latest:
        latest = s3_registry.get_latest(name)
    if not latest:
        raise HTTPException(status_code=404, detail=f"pack '{name}' has no published version")

    zip_bytes = s3_registry.get_content_zip(name, latest["version"], content_type, project_id=scope_project_id)
    if not zip_bytes:
        raise HTTPException(
            status_code=404,
            detail=f"pack '{name}' version {latest['version']} has no published {content_type}",
        )

    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"X-Pack-Version": latest["version"]},
    )


@app.post("/api/packs/{name}/fork")
def api_fork_pack(request: Request, name: str):
    project_id = _require_bearer_project(request)

    if s3_registry.project_has_fork(name, project_id):
        raise HTTPException(status_code=409, detail=f"project already has a fork of '{name}'")

    try:
        return s3_registry.fork_pack_for_project(name, project_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put("/api/packs/{name}/fork/{content_type}")
async def api_push_fork_content(request: Request, name: str, content_type: s3_registry.ContentType):
    project_id = _require_bearer_project(request)

    if not s3_registry.project_has_fork(name, project_id):
        raise HTTPException(
            status_code=404,
            detail=f"project has no fork of '{name}' yet -- run 'cartographer stack fork {name}' first",
        )

    zip_bytes = await request.body()
    s3_registry.put_content_zip(name, s3_registry.FORK_VERSION, content_type, zip_bytes, project_id=project_id)
    return {"ok": True}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


# ---------------------------------------------------------------------------
# Static SPA -- built React app (webapp/frontend/) committed into
# app/static/dist/. Mounted last so it doesn't shadow the API routes above.
# A catch-all serves index.html for any non-API path so client-side routes
# (e.g. /standards/python) work on a direct navigation or page refresh, not
# just when reached by clicking within the already-loaded SPA.
# ---------------------------------------------------------------------------

if DIST_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="spa-assets")

    @app.get("/{full_path:path}")
    def spa_catch_all(full_path: str):
        return FileResponse(DIST_DIR / "index.html")
