from pathlib import Path

from src.db import claim_next_job, create_user, enqueue_run_job, init_db


def test_enqueue_and_claim_job(tmp_path: Path) -> None:
    db_path = tmp_path / "db.sqlite"
    init_db(db_path)
    user = create_user(db_path, "a@example.com", "hash")
    run = enqueue_run_job(db_path, user.id)
    assert run.status == "QUEUED"

    job = claim_next_job(db_path)
    assert job is not None
    assert job.run_id == run.id
    assert job.status == "RUNNING"
