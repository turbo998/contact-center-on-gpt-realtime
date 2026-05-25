"""Tests for the three WS gateways — handshake, heartbeat, audit, errors.

Spec: docs/11 §11.8 acceptance + §11.2/§11.3/§11.4 message tables.
Uses FastAPI TestClient (sync websocket) — no real Foundry traffic.
"""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.audit import AuditLogger, NullSink
from app.main import create_app
from app.realtime.protocol import dumps, make_envelope
from app.session_store import SessionStore


@pytest.fixture
def client():
    audit = AuditLogger(sink=NullSink())
    store = SessionStore(audit=audit)
    app = create_app(audit=audit, store=store)
    with TestClient(app) as c:
        c.app_store = store  # type: ignore[attr-defined]
        yield c


def _frame(t: str, call_id: str, seq: int, payload: dict) -> str:
    return dumps(make_envelope(type=t, call_id=call_id, seq=seq, payload=payload))


# --- /ws/customer ---

def test_customer_handshake_emits_call_started(client: TestClient) -> None:
    with client.websocket_connect("/ws/customer?call_id=C-test1") as ws:
        ws.send_text(_frame("call.start", "C-test1", 1,
                            {"role": "customer", "lang": "zh-CN", "target_lang": "en-US"}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "call.started"
        assert msg["call_id"] == "C-test1"
        assert msg["payload"]["call_id"] == "C-test1"


def test_customer_ping_pong(client: TestClient) -> None:
    with client.websocket_connect("/ws/customer?call_id=C-ping") as ws:
        ws.send_text(_frame("call.start", "C-ping", 1,
                            {"role": "customer", "lang": "zh-CN", "target_lang": "en-US"}))
        json.loads(ws.receive_text())  # call.started

        ws.send_text(_frame("system.ping", "C-ping", 2, {}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "system.pong"


def test_customer_call_end_emits_call_ended(client: TestClient) -> None:
    with client.websocket_connect("/ws/customer?call_id=C-end") as ws:
        ws.send_text(_frame("call.start", "C-end", 1,
                            {"role": "customer", "lang": "zh-CN", "target_lang": "en-US"}))
        json.loads(ws.receive_text())  # call.started

        ws.send_text(_frame("call.end", "C-end", 2, {"reason": "user_hangup"}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "call.ended"
        assert "audit_url" in msg["payload"]


def test_customer_unknown_type_is_ignored(client: TestClient) -> None:
    """docs/11 §11.7 #3: unknown types must NOT crash the connection."""
    with client.websocket_connect("/ws/customer?call_id=C-unk") as ws:
        ws.send_text(_frame("call.start", "C-unk", 1,
                            {"role": "customer", "lang": "zh-CN", "target_lang": "en-US"}))
        json.loads(ws.receive_text())

        # Unknown type — server silently ignores; connection stays alive.
        ws.send_text(_frame("future.feature", "C-unk", 2, {"foo": "bar"}))
        ws.send_text(_frame("system.ping", "C-unk", 3, {}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "system.pong"


def test_customer_invalid_envelope_yields_error_raised(client: TestClient) -> None:
    with client.websocket_connect("/ws/customer?call_id=C-bad") as ws:
        ws.send_text(_frame("call.start", "C-bad", 1,
                            {"role": "customer", "lang": "zh-CN", "target_lang": "en-US"}))
        json.loads(ws.receive_text())

        ws.send_text("{not json")
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "error.raised"
        assert msg["payload"]["code"] == "E_INTERNAL"


def test_customer_audio_too_large_yields_error(client: TestClient) -> None:
    """docs/11 §11.8: single frame > 64 KB → E_AUDIO_TOO_LARGE."""
    with client.websocket_connect("/ws/customer?call_id=C-big") as ws:
        ws.send_text(_frame("call.start", "C-big", 1,
                            {"role": "customer", "lang": "zh-CN", "target_lang": "en-US"}))
        json.loads(ws.receive_text())

        big = "A" * (64 * 1024 + 100)
        ws.send_text(_frame("audio.frame", "C-big", 2, {"audio": big, "duration_ms": 20}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "error.raised"
        assert msg["payload"]["code"] == "E_AUDIO_TOO_LARGE"


# --- /ws/agent ---

def test_agent_handshake_and_escalate(client: TestClient) -> None:
    with client.websocket_connect("/ws/agent?call_id=A-1") as ws:
        ws.send_text(_frame("call.start", "A-1", 1,
                            {"role": "agent", "lang": "en-US", "target_lang": "zh-CN"}))
        started = json.loads(ws.receive_text())
        assert started["type"] == "call.started"

        ws.send_text(_frame("escalate.request", "A-1", 2,
                            {"order_id": "A12345", "note": "tariff waiver?"}))
        acked = json.loads(ws.receive_text())
        assert acked["type"] == "escalate.acked"
        assert "assist_ws_url" in acked["payload"]


def test_agent_escalate_missing_order_id_errors(client: TestClient) -> None:
    with client.websocket_connect("/ws/agent?call_id=A-2") as ws:
        ws.send_text(_frame("call.start", "A-2", 1,
                            {"role": "agent", "lang": "en-US", "target_lang": "zh-CN"}))
        json.loads(ws.receive_text())

        ws.send_text(_frame("escalate.request", "A-2", 2, {}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "error.raised"
        assert msg["payload"]["code"] == "E_ESCALATE_NO_CONTEXT"


# --- /ws/assist ---

def test_assist_handshake_emits_assist_started(client: TestClient) -> None:
    with client.websocket_connect("/ws/assist?call_id=AS-1") as ws:
        ws.send_text(_frame("assist.start", "AS-1", 1,
                            {"call_id": "AS-1", "context_summary": "tariff Q",
                             "order_id": "A12345", "reasoning_effort": "high"}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "assist.started"
        assert msg["payload"]["model"] == "gpt-realtime-2"
        assert msg["payload"]["reasoning_effort"] == "high"


def test_assist_without_context_rejected(client: TestClient) -> None:
    with client.websocket_connect("/ws/assist?call_id=AS-2") as ws:
        ws.send_text(_frame("assist.start", "AS-2", 1, {}))
        msg = json.loads(ws.receive_text())
        assert msg["type"] == "error.raised"
        assert msg["payload"]["code"] == "E_ESCALATE_NO_CONTEXT"


def test_assist_default_effort_high(client: TestClient) -> None:
    with client.websocket_connect("/ws/assist?call_id=AS-3") as ws:
        ws.send_text(_frame("assist.start", "AS-3", 1,
                            {"call_id": "AS-3", "context_summary": "x", "order_id": "X"}))
        msg = json.loads(ws.receive_text())
        assert msg["payload"]["reasoning_effort"] == "high"


# --- health ---

def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
