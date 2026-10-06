"""Cognito user/role management (SR.4). Replaces the AWS-console-only
bootstrap pattern SR.2 relied on for seeding test users' roles.

Users are addressed by email throughout this module and the API routes that
call it -- the pool's real `Username` attribute is an opaque UUID (since the
pool was created with `--username-attributes email`), but Cognito's Admin*
APIs accept any alias (email) interchangeably with the real username, so
there's no need to surface the UUID anywhere in this app.
"""

from __future__ import annotations

import boto3

from app.settings import settings

_cognito = boto3.client("cognito-idp", region_name=settings.aws_region)

ROLES = ("Author", "Reviewer", "Admin")


def _email_of(user: dict) -> str:
    return next((a["Value"] for a in user["Attributes"] if a["Name"] == "email"), user["Username"])


def list_users() -> list[dict]:
    users = []
    paginator = _cognito.get_paginator("list_users")
    for page in paginator.paginate(UserPoolId=settings.cognito_pool_id):
        for u in page["Users"]:
            email = _email_of(u)
            groups_resp = _cognito.admin_list_groups_for_user(UserPoolId=settings.cognito_pool_id, Username=email)
            groups = [g["GroupName"] for g in groups_resp["Groups"]]
            users.append({"email": email, "groups": groups})
    return sorted(users, key=lambda u: u["email"])


def set_user_groups(email: str, groups: list[str]) -> dict:
    """Sets the user's group membership to exactly `groups` -- adds what's
    missing, removes what's no longer wanted. Not additive-only, since an
    Admin revoking a role needs to actually take effect."""
    invalid = set(groups) - set(ROLES)
    if invalid:
        raise ValueError(f"not a valid role: {', '.join(sorted(invalid))}")

    current = {
        g["GroupName"]
        for g in _cognito.admin_list_groups_for_user(UserPoolId=settings.cognito_pool_id, Username=email)["Groups"]
    }
    target = set(groups)

    for group in current - target:
        _cognito.admin_remove_user_from_group(UserPoolId=settings.cognito_pool_id, Username=email, GroupName=group)
    for group in target - current:
        _cognito.admin_add_user_to_group(UserPoolId=settings.cognito_pool_id, Username=email, GroupName=group)

    return {"email": email, "groups": sorted(target)}
