"""In-memory session store for active calls.

Spec: docs/05 §5.2 (session-store), docs/11 (call_id, audit_url).

A ``Session`` represents one active call (one ``call_id``). It owns:
- ws-side metadata (role, started_at, lang, target_lang)
- a per-session ``AuditLogger`` handle (so all three WS endpoints write the
  same audit file)
- a monotonic outbound seq counter shared across all server→client envelopes
  for this call_id (docs/11 §11.1.1)
- a short ``escalate_context`` slot populated when /ws/agent receives
  ``escalate.request`` — consumed when /ws/assist opens for the same call_id

The store is process-local and dict-backed. Concurrent multi-call demo
traffic is fine; HA / multi-pod is out of scope (single-pod ACA deploy).
"""
from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any

from app.audit import AuditLogger


@dataclass
class Session:
    call_id: str
    role: str  # "customer" | "agent"
    lang: str
    target_lang: str
    started_at_ms: int
    audit: AuditLogger
    _seq: int = 0
    escalate_context: dict[str, Any] | None = None
    ended_at_ms: int | None = None

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def duration_ms(self) -> int:
        end = self.ended_at_ms if self.ended_at_ms is not None else int(time.time() * 1000)
        return end - self.started_at_ms


class SessionStore:
    def __init__(self, audit: AuditLogger) -> None:
        self._sessions: dict[str, Session] = {}
        self._refs: dict[str, int] = {}
        self._audit = audit
        self._lock = asyncio.Lock()

    async def create(
        self,
        *,
        call_id: str,
        role: str,
        lang: str,
        target_lang: str,
    ) -> Session:
        async with self._lock:
            existing = self._sessions.get(call_id)
            if existing is not None:
                # Idempotent attach: same call_id can be joined by multiple
                # channels (customer + agent + assist). Refcount tracks
                # detaches so the session lives until the last one leaves.
                self._refs[call_id] += 1
                return existing
            sess = Session(
                call_id=call_id,
                role=role,
                lang=lang,
                target_lang=target_lang,
                started_at_ms=int(time.time() * 1000),
                audit=self._audit,
            )
            self._sessions[call_id] = sess
            self._refs[call_id] = 1
            return sess

    def get(self, call_id: str) -> Session | None:
        return self._sessions.get(call_id)

    async def end(self, call_id: str) -> Session | None:
        async with self._lock:
            sess = self._sessions.get(call_id)
            if sess is None:
                return None
            sess.ended_at_ms = int(time.time() * 1000)
            return sess

    async def remove(self, call_id: str) -> None:
        async with self._lock:
            if call_id not in self._refs:
                return
            self._refs[call_id] -= 1
            if self._refs[call_id] <= 0:
                self._refs.pop(call_id, None)
                self._sessions.pop(call_id, None)

    def active_count(self) -> int:
        return len(self._sessions)
