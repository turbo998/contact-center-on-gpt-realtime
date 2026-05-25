"""Tests for backend/app/audit.py — append-only JSONL session logger.

Spec: docs/05 §5.2 (audit-logger), docs/02 step 6 (audit-{call_id}.jsonl
must contain whisper raw, translate parallel, rt-2 reasoning + tool calls).
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app.audit import AuditLogger, JsonlFileSink, NullSink

# -------------------- JsonlFileSink --------------------


@pytest.mark.asyncio
async def test_jsonl_sink_writes_one_line_per_record(tmp_path: Path) -> None:
    sink = JsonlFileSink(tmp_path)
    await sink.write("sess-1", {"type": "a", "n": 1})
    await sink.write("sess-1", {"type": "b", "n": 2})
    await sink.close("sess-1")

    p = tmp_path / "audit-sess-1.jsonl"
    assert p.exists()
    lines = p.read_text().strip().splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0]) == {"type": "a", "n": 1}
    assert json.loads(lines[1]) == {"type": "b", "n": 2}


@pytest.mark.asyncio
async def test_jsonl_sink_appends_and_isolates_sessions(tmp_path: Path) -> None:
    sink = JsonlFileSink(tmp_path)
    await sink.write("sess-A", {"v": 1})
    await sink.write("sess-B", {"v": 2})
    await sink.write("sess-A", {"v": 3})
    await sink.close("sess-A")
    await sink.close("sess-B")

    a = (tmp_path / "audit-sess-A.jsonl").read_text().strip().splitlines()
    b = (tmp_path / "audit-sess-B.jsonl").read_text().strip().splitlines()
    assert [json.loads(x)["v"] for x in a] == [1, 3]
    assert [json.loads(x)["v"] for x in b] == [2]


@pytest.mark.asyncio
async def test_jsonl_sink_rejects_unsafe_session_id(tmp_path: Path) -> None:
    sink = JsonlFileSink(tmp_path)
    for bad in ["../escape", "a/b", "with space", "", "."]:
        with pytest.raises(ValueError):
            await sink.write(bad, {"v": 1})


@pytest.mark.asyncio
async def test_jsonl_sink_concurrent_writes_dont_interleave(tmp_path: Path) -> None:
    sink = JsonlFileSink(tmp_path)

    async def write_many(prefix: str, n: int) -> None:
        for i in range(n):
            await sink.write("sess-x", {"p": prefix, "i": i})

    await asyncio.gather(
        write_many("A", 50),
        write_many("B", 50),
        write_many("C", 50),
    )
    await sink.close("sess-x")

    lines = (tmp_path / "audit-sess-x.jsonl").read_text().strip().splitlines()
    assert len(lines) == 150
    # Every line is a valid full record (no torn writes).
    for line in lines:
        rec = json.loads(line)
        assert rec["p"] in {"A", "B", "C"}
        assert isinstance(rec["i"], int)


# -------------------- AuditLogger --------------------


@pytest.mark.asyncio
async def test_audit_logger_logs_event_with_ts_and_envelope_passthrough(
    tmp_path: Path,
) -> None:
    logger = AuditLogger(sink=JsonlFileSink(tmp_path))
    await logger.log_event(
        "sess-1",
        envelope={"v": 1, "type": "translate.text.delta", "payload": {"text": "hi"}},
        direction="server_to_agent",
    )
    await logger.close("sess-1")

    rec = json.loads((tmp_path / "audit-sess-1.jsonl").read_text().strip())
    assert rec["kind"] == "ws_event"
    assert rec["direction"] == "server_to_agent"
    assert rec["envelope"]["type"] == "translate.text.delta"
    assert isinstance(rec["ts_ms"], int)


@pytest.mark.asyncio
async def test_audit_logger_logs_model_io_redacts_audio(tmp_path: Path) -> None:
    logger = AuditLogger(sink=JsonlFileSink(tmp_path))
    await logger.log_model_io(
        "sess-1",
        model="gpt-realtime-translate",
        direction="model_out",
        event_type="response.audio.delta",
        payload={"delta": "QUJDREVGRw==" * 500, "transcript": "hello"},
    )
    await logger.close("sess-1")

    rec = json.loads((tmp_path / "audit-sess-1.jsonl").read_text().strip())
    assert rec["kind"] == "model_io"
    assert rec["model"] == "gpt-realtime-translate"
    # Audio base64 redacted — only length preserved for forensic use.
    assert rec["payload"]["delta"] == {"__redacted__": "base64-audio", "len": 6000}
    assert rec["payload"]["transcript"] == "hello"


@pytest.mark.asyncio
async def test_audit_logger_logs_tool_call_round_trip(tmp_path: Path) -> None:
    logger = AuditLogger(sink=JsonlFileSink(tmp_path))
    await logger.log_tool_call(
        "sess-1",
        call_id="cid_1",
        name="get_order",
        arguments={"order_id": "A12345"},
        result={"found": True, "order_id": "A12345"},
        latency_ms=42,
    )
    await logger.close("sess-1")

    rec = json.loads((tmp_path / "audit-sess-1.jsonl").read_text().strip())
    assert rec["kind"] == "tool_call"
    assert rec["name"] == "get_order"
    assert rec["call_id"] == "cid_1"
    assert rec["arguments"] == {"order_id": "A12345"}
    assert rec["result"]["found"] is True
    assert rec["latency_ms"] == 42


@pytest.mark.asyncio
async def test_audit_logger_logs_reasoning_summary(tmp_path: Path) -> None:
    logger = AuditLogger(sink=JsonlFileSink(tmp_path))
    await logger.log_reasoning("sess-1", trace="step1\nstep2", effort="medium")
    await logger.close("sess-1")

    rec = json.loads((tmp_path / "audit-sess-1.jsonl").read_text().strip())
    assert rec["kind"] == "reasoning"
    assert rec["effort"] == "medium"
    assert rec["trace"] == "step1\nstep2"


@pytest.mark.asyncio
async def test_audit_logger_six_step_scenario_parses_clean(tmp_path: Path) -> None:
    """End-to-end: simulate the 6-step business scenario, ensure full JSONL parse."""
    logger = AuditLogger(sink=JsonlFileSink(tmp_path))
    sid = "C-2026-001"

    # Step 1-2: bilingual chat (translate + whisper deltas)
    await logger.log_event(sid, envelope={"v": 1, "type": "session.started", "payload": {}}, direction="client_to_server")
    await logger.log_model_io(sid, model="gpt-realtime-translate", direction="model_out", event_type="response.text.delta", payload={"delta": "你好"})
    await logger.log_model_io(sid, model="gpt-realtime-mini-transcribe", direction="model_out", event_type="conversation.item.input_audio_transcription.delta", payload={"delta": "hello"})

    # Step 3: escalate
    await logger.log_event(sid, envelope={"v": 1, "type": "escalate.requested", "payload": {}}, direction="client_to_server")

    # Step 4: rt-2 reasoning + tools
    await logger.log_reasoning(sid, trace="check order, then tariff, then insurance", effort="high")
    await logger.log_tool_call(sid, call_id="c1", name="get_order", arguments={"order_id": "A12345"}, result={"found": True}, latency_ms=120)
    await logger.log_tool_call(sid, call_id="c2", name="check_tariff", arguments={"from_country": "cn", "to_country": "gb", "sku": "coffee-maker"}, result={"found": True}, latency_ms=180)
    await logger.log_tool_call(sid, call_id="c3", name="check_insurance", arguments={"policy_id": "INS-7788"}, result={"found": True}, latency_ms=150)

    # Step 5: AI reply
    await logger.log_model_io(sid, model="gpt-realtime-2", direction="model_out", event_type="response.audio.delta", payload={"delta": "base64-audio-here" * 100})

    # Step 6: call ended
    await logger.log_event(sid, envelope={"v": 1, "type": "call.ended", "payload": {"duration_ms": 60000}}, direction="server_to_agent")

    await logger.close(sid)

    p = tmp_path / f"audit-{sid}.jsonl"
    lines = p.read_text().strip().splitlines()
    assert len(lines) == 10
    records = [json.loads(ln) for ln in lines]
    kinds = [r["kind"] for r in records]
    assert kinds.count("ws_event") == 3
    assert kinds.count("model_io") == 3
    assert kinds.count("tool_call") == 3
    assert kinds.count("reasoning") == 1
    # Timestamps monotonic-ish (ms granularity may tie).
    ts = [r["ts_ms"] for r in records]
    assert ts == sorted(ts)


# -------------------- NullSink --------------------


@pytest.mark.asyncio
async def test_null_sink_no_op(tmp_path: Path) -> None:
    sink = NullSink()
    await sink.write("anything", {"x": 1})
    await sink.close("anything")
    # No files created.
    files = list(tmp_path.iterdir())  # noqa: ASYNC240
    assert files == []
