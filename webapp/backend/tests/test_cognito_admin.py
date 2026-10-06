"""Cognito user/role management (app/cognito_admin.py), against a mocked
boto3 cognito-idp client -- no real AWS calls. Live verification of the
Admin* API's email-alias behavior was done manually against the real pool
(see project memory / sr-4 status note), not re-asserted here."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app import cognito_admin


def test_list_users_returns_email_and_groups_sorted_by_email():
    mock_client = MagicMock()
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = [
        {
            "Users": [
                {"Username": "uuid-1", "Attributes": [{"Name": "email", "Value": "b@example.com"}]},
                {"Username": "uuid-2", "Attributes": [{"Name": "email", "Value": "a@example.com"}]},
            ]
        }
    ]
    mock_client.get_paginator.return_value = mock_paginator
    mock_client.admin_list_groups_for_user.side_effect = [
        {"Groups": [{"GroupName": "Author"}]},
        {"Groups": [{"GroupName": "Admin"}, {"GroupName": "Reviewer"}]},
    ]

    with patch.object(cognito_admin, "_cognito", mock_client):
        result = cognito_admin.list_users()

    assert result == [
        {"email": "a@example.com", "groups": ["Admin", "Reviewer"]},
        {"email": "b@example.com", "groups": ["Author"]},
    ]


def test_set_user_groups_rejects_invalid_role():
    with pytest.raises(ValueError, match="SuperAdmin"):
        cognito_admin.set_user_groups("a@example.com", ["SuperAdmin"])


def test_set_user_groups_adds_and_removes_to_match_target():
    mock_client = MagicMock()
    mock_client.admin_list_groups_for_user.return_value = {
        "Groups": [{"GroupName": "Author"}, {"GroupName": "Reviewer"}]
    }

    with patch.object(cognito_admin, "_cognito", mock_client):
        result = cognito_admin.set_user_groups("a@example.com", ["Reviewer", "Admin"])

    mock_client.admin_remove_user_from_group.assert_called_once_with(
        UserPoolId=cognito_admin.settings.cognito_pool_id, Username="a@example.com", GroupName="Author"
    )
    mock_client.admin_add_user_to_group.assert_called_once_with(
        UserPoolId=cognito_admin.settings.cognito_pool_id, Username="a@example.com", GroupName="Admin"
    )
    assert result == {"email": "a@example.com", "groups": ["Admin", "Reviewer"]}


def test_set_user_groups_no_changes_when_already_matching():
    mock_client = MagicMock()
    mock_client.admin_list_groups_for_user.return_value = {"Groups": [{"GroupName": "Author"}]}

    with patch.object(cognito_admin, "_cognito", mock_client):
        cognito_admin.set_user_groups("a@example.com", ["Author"])

    mock_client.admin_remove_user_from_group.assert_not_called()
    mock_client.admin_add_user_to_group.assert_not_called()
