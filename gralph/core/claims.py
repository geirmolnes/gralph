"""Claim/lease helpers for multi-agent task coordination."""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import time

CLAIMS_FILE = "claims.json"
LOCK_FILE = "claims.lock"
DEFAULT_LEASE_SECONDS = 90 * 60
LOCK_TIMEOUT_SECONDS = 5.0
LOCK_POLL_SECONDS = 0.05
LOCK_STALE_SECONDS = 30.0


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _claims_path(gralph_dir: Path) -> Path:
    return gralph_dir / CLAIMS_FILE


def _lock_path(gralph_dir: Path) -> Path:
    return gralph_dir / LOCK_FILE


@contextmanager
def _claims_lock(gralph_dir: Path):
    """Best-effort inter-process lock for claims read/modify/write operations."""
    lock_path = _lock_path(gralph_dir)
    deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
    fd: int | None = None

    while True:
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                age = time.time() - lock_path.stat().st_mtime
                if age > LOCK_STALE_SECONDS:
                    lock_path.unlink(missing_ok=True)
                    continue
            except OSError:
                pass

            if time.monotonic() >= deadline:
                raise TimeoutError(f"Timed out waiting for claims lock: {lock_path}")
            time.sleep(LOCK_POLL_SECONDS)

    try:
        if fd is not None:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(f"{os.getpid()}\n")
                handle.flush()
        yield
    finally:
        lock_path.unlink(missing_ok=True)


def _parse_timestamp(value: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def default_owner() -> str:
    """Get default claim owner from environment."""
    return os.environ.get("USER") or os.environ.get("USERNAME") or "gralph"


def _read_claims(gralph_dir: Path) -> dict[str, dict[str, str]]:
    path = _claims_path(gralph_dir)
    if not path.exists():
        return {}

    try:
        payload = json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return {}

    claims = payload.get("claims", {})
    if not isinstance(claims, dict):
        return {}

    normalized: dict[str, dict[str, str]] = {}
    for task_id, claim in claims.items():
        if not isinstance(task_id, str) or not isinstance(claim, dict):
            continue
        owner = claim.get("owner")
        claimed_at = claim.get("claimed_at")
        lease_until = claim.get("lease_until")
        if not all(isinstance(v, str) for v in [owner, claimed_at, lease_until]):
            continue
        normalized[task_id] = {
            "owner": owner,
            "claimed_at": claimed_at,
            "lease_until": lease_until,
        }
    return normalized


def _write_claims(gralph_dir: Path, claims: dict[str, dict[str, str]]) -> None:
    path = _claims_path(gralph_dir)
    payload = {"claims": claims}
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")


def _partition_claims(
    claims: dict[str, dict[str, str]],
    now: datetime,
) -> tuple[dict[str, dict[str, str]], list[dict[str, str]]]:
    active: dict[str, dict[str, str]] = {}
    stale: list[dict[str, str]] = []
    for task_id, claim in claims.items():
        lease_until = _parse_timestamp(claim.get("lease_until", ""))
        if lease_until is None or lease_until <= now:
            stale.append(
                {
                    "task_id": task_id,
                    "owner": claim.get("owner", ""),
                    "claimed_at": claim.get("claimed_at", ""),
                    "lease_until": claim.get("lease_until", ""),
                }
            )
            continue
        active[task_id] = claim
    return active, stale


def _prune_expired_claims_unlocked(
    gralph_dir: Path,
    current: datetime,
) -> list[dict[str, str]]:
    """Remove expired claims and return stale entries (caller must hold lock)."""
    claims = _read_claims(gralph_dir)
    active, stale = _partition_claims(claims, current)
    if stale:
        _write_claims(gralph_dir, active)
    return stale


def prune_expired_claims(
    gralph_dir: Path,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    """Remove expired claims and return the stale entries that were removed."""
    current = now or _utc_now()
    try:
        with _claims_lock(gralph_dir):
            return _prune_expired_claims_unlocked(
                gralph_dir,
                current=current,
            )
    except TimeoutError:
        return []


def get_active_claims(
    gralph_dir: Path,
    now: datetime | None = None,
) -> dict[str, dict[str, str]]:
    """Return currently-active claims (prunes expired claims first)."""
    current = now or _utc_now()
    try:
        with _claims_lock(gralph_dir):
            _prune_expired_claims_unlocked(gralph_dir, current=current)
            return _read_claims(gralph_dir)
    except TimeoutError:
        return _read_claims(gralph_dir)


def get_stale_claims(
    gralph_dir: Path,
    now: datetime | None = None,
) -> list[dict[str, str]]:
    """Return stale claims without modifying files."""
    current = now or _utc_now()
    try:
        with _claims_lock(gralph_dir):
            claims = _read_claims(gralph_dir)
            _, stale = _partition_claims(claims, current)
            return stale
    except TimeoutError:
        return []


def claim_task(
    gralph_dir: Path,
    task_id: str,
    owner: str,
    lease_seconds: int = DEFAULT_LEASE_SECONDS,
    now: datetime | None = None,
) -> tuple[bool, str | None]:
    """
    Claim or renew a task claim.

    Returns:
        (ok, current_owner_if_claimed_by_other)
    """
    current = now or _utc_now()
    try:
        with _claims_lock(gralph_dir):
            _prune_expired_claims_unlocked(gralph_dir, current=current)
            claims = _read_claims(gralph_dir)

            existing = claims.get(task_id)
            if existing and existing.get("owner") != owner:
                return False, existing.get("owner")

            lease_until = current + timedelta(seconds=max(1, lease_seconds))
            claims[task_id] = {
                "owner": owner,
                "claimed_at": current.isoformat(),
                "lease_until": lease_until.isoformat(),
            }
            _write_claims(gralph_dir, claims)
            return True, None
    except TimeoutError:
        return False, None


def release_claim(
    gralph_dir: Path,
    task_id: str,
    owner: str | None = None,
    reason: str = "released",
    now: datetime | None = None,
) -> bool:
    """Release an active claim."""
    _ = reason
    current = now or _utc_now()
    try:
        with _claims_lock(gralph_dir):
            _prune_expired_claims_unlocked(gralph_dir, current=current)
            claims = _read_claims(gralph_dir)

            existing = claims.get(task_id)
            if not existing:
                return False
            if owner is not None and existing.get("owner") != owner:
                return False

            del claims[task_id]
            _write_claims(gralph_dir, claims)
            return True
    except TimeoutError:
        return False
