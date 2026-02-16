from datetime import datetime, timedelta, timezone
import os
import time

from gralph.core.claims import (
    claim_task,
    get_active_claims,
    get_stale_claims,
    prune_expired_claims,
    release_claim,
)


def _dt(hours: int = 0) -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=hours)


def test_claim_task_conflict_and_release_flow(tmp_path):
    gralph_dir = tmp_path / ".gralph_planning"
    gralph_dir.mkdir()

    ok, conflict_owner = claim_task(
        gralph_dir, "g-a1b2", owner="alice", lease_seconds=3600, now=_dt()
    )
    assert ok is True
    assert conflict_owner is None

    ok, conflict_owner = claim_task(
        gralph_dir, "g-a1b2", owner="bob", lease_seconds=3600, now=_dt()
    )
    assert ok is False
    assert conflict_owner == "alice"

    # Owner mismatch cannot release.
    assert release_claim(gralph_dir, "g-a1b2", owner="bob") is False
    assert release_claim(gralph_dir, "g-a1b2", owner="alice") is True
    assert get_active_claims(gralph_dir) == {}


def test_stale_claim_detection_and_prune(tmp_path):
    gralph_dir = tmp_path / ".gralph_planning"
    gralph_dir.mkdir()

    now = _dt()
    # Active claim
    claim_task(gralph_dir, "g-new1", owner="alice", lease_seconds=3600, now=now)
    # Expired claim
    claim_task(gralph_dir, "g-old1", owner="alice", lease_seconds=1, now=now - timedelta(hours=2))

    stale = get_stale_claims(gralph_dir, now=now)
    stale_ids = {c["task_id"] for c in stale}
    assert stale_ids == {"g-old1"}

    pruned = prune_expired_claims(gralph_dir, now=now)
    assert {c["task_id"] for c in pruned} == {"g-old1"}
    assert set(get_active_claims(gralph_dir, now=now).keys()) == {"g-new1"}


def test_claim_task_recovers_from_stale_lock_file(tmp_path):
    gralph_dir = tmp_path / ".gralph_planning"
    gralph_dir.mkdir()
    lock_file = gralph_dir / "claims.lock"
    lock_file.write_text("stale\n")
    stale_ts = time.time() - 120
    os.utime(lock_file, (stale_ts, stale_ts))

    ok, conflict_owner = claim_task(gralph_dir, "g-a1b2", owner="alice", lease_seconds=60)
    assert ok is True
    assert conflict_owner is None
    assert lock_file.exists() is False
