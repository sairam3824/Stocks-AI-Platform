from pathlib import Path

from src.db import (
    create_user,
    get_user_by_email,
    get_user_by_email_verification_token,
    get_user_by_reset_token,
    get_user_workspace_id,
    get_workspace_member_role,
    init_db,
    set_password_reset_token,
    update_user_password,
    verify_user_email,
)


def test_email_verification_token_flow(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    init_db(db_path)
    user = create_user(
        db_path,
        "verify@example.com",
        "hash",
        email_verified=0,
        email_verification_token="verify-token-1",
    )

    token_user = get_user_by_email_verification_token(db_path, "verify-token-1")
    assert token_user is not None
    assert token_user.id == user.id
    assert token_user.email_verified == 0

    verify_user_email(db_path, user.id)
    verified = get_user_by_email(db_path, "verify@example.com")
    assert verified is not None
    assert verified.email_verified == 1
    assert verified.email_verification_token == ""


def test_password_reset_token_flow(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    init_db(db_path)
    user = create_user(db_path, "reset@example.com", "hash")
    set_password_reset_token(
        db_path,
        user.id,
        token="reset-token-1",
        expires_at="9999-12-31 23:59:59",
    )
    token_user = get_user_by_reset_token(db_path, "reset-token-1")
    assert token_user is not None
    assert token_user.id == user.id

    update_user_password(db_path, user.id, "hash-2")
    token_user_after = get_user_by_reset_token(db_path, "reset-token-1")
    assert token_user_after is None


def test_default_workspace_role_is_owner(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    init_db(db_path)
    user = create_user(db_path, "owner@example.com", "hash")
    workspace_id = get_user_workspace_id(db_path, user.id)
    role = get_workspace_member_role(db_path, user.id, workspace_id)
    assert role == "owner"
