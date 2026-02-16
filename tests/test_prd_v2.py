import re

from gralph.core.prd import ensure_task_ids, get_ready_tasks


def test_ensure_task_ids_adds_missing_ids_and_preserves_existing():
    prd = """\
# PRD

- [ ] Add auth middleware ||| uv run pytest tests/test_auth.py
- [ ] [id:g-ffff] Add metrics endpoint ||| uv run pytest tests/test_metrics.py
"""
    updated, added = ensure_task_ids(prd)

    assert added == 1
    assert "[id:g-ffff]" in updated
    assert re.search(r"\[id:g-[0-9a-f]{4}\] Add auth middleware", updated)


def test_get_ready_tasks_respects_dependencies_and_claim_filter():
    prd = """\
# PRD

- [x] [id:g-1000] Build auth core ||| uv run pytest tests/test_auth_core.py
- [ ] [id:g-2000] Build API auth guard [deps:g-1000] ||| uv run pytest tests/test_guard.py
- [ ] [id:g-3000] Build docs [deps:g-2000] ||| uv run pytest tests/test_docs.py
"""
    ready = get_ready_tasks(prd)
    assert [t.task_id for t in ready] == ["g-2000"]

    # Claimed tasks are excluded.
    ready_unclaimed = get_ready_tasks(prd, unavailable_task_ids={"g-2000"})
    assert ready_unclaimed == []


def test_get_ready_tasks_treats_skipped_and_failed_as_terminal():
    prd = """\
- [~] [id:g-1000] Optional integration path ||| test -f /tmp/none
- [!] [id:g-2000] Legacy migration path ||| test -f /tmp/none
- [ ] [id:g-3000] Continue rollout [deps:g-1000,g-2000] ||| uv run pytest tests/test_rollout.py
"""
    ready = get_ready_tasks(prd)
    assert [t.task_id for t in ready] == ["g-3000"]


def test_ensure_task_ids_rewrites_duplicate_ids():
    prd = """\
- [ ] [id:g-1111] Build auth ||| uv run pytest tests/test_auth.py
- [ ] [id:g-1111] Build docs ||| uv run pytest tests/test_docs.py
"""
    updated, changed = ensure_task_ids(prd)

    ids = re.findall(r"\[id:([^\]]+)\]", updated)
    assert changed == 1
    assert ids[0] == "g-1111"
    assert ids[1] != "g-1111"
