from pathlib import Path

from src.db import create_user, get_model_profile, get_user_workspace_id, init_db, upsert_model_profile


def test_upsert_and_get_model_profile(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    init_db(db_path)
    user = create_user(db_path, "model@example.com", "hash")
    workspace_id = get_user_workspace_id(db_path, user.id)

    upsert_model_profile(
        db_path,
        user_id=user.id,
        workspace_id=workspace_id,
        symbol="AAPL",
        horizon="monthly",
        preferred_model="stat",
        last_mape=2.5,
        last_rmse=1.2,
    )
    row = get_model_profile(db_path, user.id, workspace_id, "AAPL", "monthly")
    assert row is not None
    assert row.preferred_model == "stat"
    assert row.sample_count == 1

    upsert_model_profile(
        db_path,
        user_id=user.id,
        workspace_id=workspace_id,
        symbol="AAPL",
        horizon="monthly",
        preferred_model="best",
        last_mape=2.1,
        last_rmse=1.0,
    )
    updated = get_model_profile(db_path, user.id, workspace_id, "AAPL", "monthly")
    assert updated is not None
    assert updated.preferred_model == "best"
    assert updated.sample_count >= 2
