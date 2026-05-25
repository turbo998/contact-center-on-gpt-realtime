"""Foundry Realtime session.update payloads — single source of truth.

These dicts mirror docs/12-realtime-session-config.md §12.2/§12.3/§12.4 exactly
and are imported by:
  - backend/scripts/smoke_translate.py  (#4)
  - backend/scripts/smoke_whisper.py    (#5)
  - backend/scripts/smoke_assistant.py  (#6)
  - backend/app/realtime/{translate,whisper,assistant}.py  (#8+)

Any change here must be matched in docs/12 (tests enforce this).
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

__all__ = [
    "TRANSLATE_SESSION",
    "WHISPER_SESSION",
    "ASSISTANT_SESSION",
    "get_session",
]


# --- §12.2 translate ---------------------------------------------------------
TRANSLATE_SESSION: dict[str, Any] = {
    "modalities": ["audio", "text"],
    "instructions": (
        "你是一个实时双向口译员。规则："
        "(1) 听到中文(zh-CN)立即翻成英文(en-US) 输出；"
        "(2) 听到英文立即翻成中文输出；"
        "(3) 严格逐句、忠实、流畅，不增不减；"
        "(4) 遇到订单号/SKU/数字串直接保留原样不翻译；"
        "(5) 不要寒暄、不要解释、不要拒绝，只输出译文；"
        "(6) 如果听到无意义噪音或静音，不要输出。"
    ),
    "voice": "alloy",
    "input_audio_format": "pcm16",
    "output_audio_format": "pcm16",
    "input_audio_transcription": None,
    "turn_detection": {
        "type": "server_vad",
        "threshold": 0.5,
        "prefix_padding_ms": 300,
        "silence_duration_ms": 500,
        "create_response": True,
    },
    "temperature": 0.6,
    "max_response_output_tokens": 4096,
    "tools": [],
    "tool_choice": "none",
}


# --- §12.3 whisper -----------------------------------------------------------
WHISPER_SESSION: dict[str, Any] = {
    "modalities": ["text"],
    "instructions": (
        "你是流式语音转写引擎。规则："
        "(1) 严格按听到的内容转写，不要翻译、不要润色、不要总结；"
        "(2) 中文输出简体，英文输出原文；"
        "(3) 标点按自然停顿；"
        "(4) 数字/订单号保留原始形式；"
        "(5) 不要输出无意义内容（如咳嗽、纯静音）。"
    ),
    "voice": None,
    "input_audio_format": "pcm16",
    "output_audio_format": None,
    "input_audio_transcription": {
        "model": "whisper-1",
        "language": None,
        "prompt": "客服售后 订单号 关税 保险 退货 换新 物流 SKU",
    },
    "turn_detection": {
        "type": "server_vad",
        "threshold": 0.5,
        "prefix_padding_ms": 300,
        "silence_duration_ms": 700,
        "create_response": False,
    },
    "temperature": 0.0,
    "tools": [],
    "tool_choice": "none",
}


# --- §12.4 assistant ---------------------------------------------------------
ASSISTANT_SESSION: dict[str, Any] = {
    "modalities": ["audio", "text"],
    "instructions": (
        "你是跨境电商客服 AI 助理。你的客户是英国总部的一线坐席，"
        "他们刚把一通复杂的中文客户来电升级给你处理。\n\n"
        "工作规则：\n"
        "1. 收到 escalate 时，上下文会包含：最近 30 秒对话摘要 + 客户订单号 + 客户诉求要点。\n"
        "2. 你**必须**先调用 get_order(order_id) 拿到订单详情。\n"
        "3. 如果涉及关税/进口费用，**必须**调用 check_tariff(from_country, to_country, sku)。\n"
        "4. 如果客户提到保险或希望免运费，**必须**调用 check_insurance(policy_id)。\n"
        "5. 工具调用完成后，给出**一个明确的方案**（A/B 二选一即可），"
        "用**简体中文**回复（要让客户听得懂），语速适中。\n"
        "6. 回复结构：诉求确认 → 方案 → 关键金额/时间 → 请客户确认。\n"
        "7. 总字数控制在 80–150 字，避免冗长。\n"
        "8. 推理过程（reasoning）会被坐席看到，所以思考链请用中文、要点式表述。\n"
        "9. 不要承诺超出工具返回结果之外的内容（不要幻觉编造金额、政策）。\n"
        "10. 如果工具返回 not_found 或失败，明确告诉客户'需要人工进一步核实'，不要瞎编。"
    ),
    "voice": "marin",
    "input_audio_format": "pcm16",
    "output_audio_format": "pcm16",
    "input_audio_transcription": {"model": "whisper-1", "language": "zh"},
    "turn_detection": {
        "type": "server_vad",
        "threshold": 0.5,
        "prefix_padding_ms": 300,
        "silence_duration_ms": 600,
        "create_response": True,
    },
    "temperature": 0.7,
    "max_response_output_tokens": 1024,
    "reasoning": {"effort": "high"},
    "tools": [
        {
            "type": "function",
            "name": "get_order",
            "description": "查询订单详情。返回订单的 sku、收货国、发货国、状态、金额。",
            "parameters": {
                "type": "object",
                "properties": {
                    "order_id": {"type": "string", "description": "订单号，例如 A12345"}
                },
                "required": ["order_id"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "check_tariff",
            "description": "查询某 SKU 从一个国家到另一个国家的关税金额（GBP）。",
            "parameters": {
                "type": "object",
                "properties": {
                    "from_country": {
                        "type": "string",
                        "description": "ISO 3166-1 alpha-2 国家码，如 CN",
                    },
                    "to_country": {
                        "type": "string",
                        "description": "ISO 3166-1 alpha-2 国家码，如 GB",
                    },
                    "sku": {"type": "string", "description": "商品 SKU，如 COFFEE-MAKER"},
                },
                "required": ["from_country", "to_country", "sku"],
                "additionalProperties": False,
            },
        },
        {
            "type": "function",
            "name": "check_insurance",
            "description": "查询保险单是否覆盖跨境运费或关税。",
            "parameters": {
                "type": "object",
                "properties": {
                    "policy_id": {"type": "string", "description": "保险单号，如 INS-7788"}
                },
                "required": ["policy_id"],
                "additionalProperties": False,
            },
        },
    ],
    "tool_choice": "auto",
}


_SESSIONS: dict[str, dict[str, Any]] = {
    "translate": TRANSLATE_SESSION,
    "whisper": WHISPER_SESSION,
    "assistant": ASSISTANT_SESSION,
}


def get_session(kind: str) -> dict[str, Any]:
    """Return a deep copy of the named session config.

    Always returns a copy so callers can mutate without polluting the SOT.
    """
    if kind not in _SESSIONS:
        raise ValueError(
            f"unknown session kind: {kind!r} (expected one of {sorted(_SESSIONS)})"
        )
    return deepcopy(_SESSIONS[kind])
