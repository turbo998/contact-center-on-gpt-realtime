"""Tests for SessionStore multi-channel attach/detach (issue #47).

One logical call carries 3 channels (customer, agent, assist) that all
share one `call_id`. `create` must be idempotent (refcount-based attach)
and `remove` must only delete the session on the final detach.
"""
from __future__ import annotations

import pytest

from app.audit import AuditLogger, NullSink
from app.session_store import SessionStore


@pytest.fixture
def store() -> SessionStore:
    return SessionStore(audit=AuditLogger(NullSink()))


@pytest.mark.asyncio
async def test_attach_same_call_id_returns_same_session(store: SessionStore) -> None:
    a = await store.create(call_id="C-1", role="customer", lang="zh-CN", target_lang="en-US")
    b = await store.create(call_id="C-1", role="agent", lang="en-US", target_lang="zh-CN")
    c = await store.create(call_id="C-1", role="assist", lang="zh-CN", target_lang="zh-CN")
    assert a is b is c


@pytest.mark.asyncio
async def test_session_survives_until_last_detach(store: SessionStore) -> None:
    await store.create(call_id="C-2", role="customer", lang="zh-CN", target_lang="en-US")
    await store.create(call_id="C-2", role="agent", lang="en-US", target_lang="zh-CN")

    await store.remove("C-2")
    assert store.get("C-2") is not None, "session must outlive first detach"

    await store.remove("C-2")
    assert store.get("C-2") is None, "session must be gone after last detach"


@pytest.mark.asyncio
async def test_remove_unknown_is_noop(store: SessionStore) -> None:
    await store.remove("does-not-exist")  # must not raise
