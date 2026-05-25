# 11 · API Contract（WebSocket 协议详细设计）

> 本文是 **开发者直接照着写代码** 的契约级文档。
> 前后端任何对 WebSocket 消息结构有疑问，以本文为唯一真实来源（Single Source of Truth）。
> 如与 Foundry/OpenAI 官方 Realtime API 字段冲突（例如未来协议升级），以官方为准、本文随之修订。

---

## 11.1 通用约定

### 11.1.1 消息信封（Envelope）

所有 WebSocket 消息均为 **JSON 文本帧**，统一信封：

```jsonc
{
  "v": 1,                       // 协议大版本，breaking change 时 +1
  "type": "namespace.action",   // 见 §11.2 ~ §11.4
  "ts": 1748131234567,          // 服务端/客户端本地毫秒时间戳
  "call_id": "C-20260525-001",  // 通话 ID，每条消息携带，便于多通话隔离
  "seq": 42,                    // 同一通话内单调递增（断线重连后重置）
  "payload": { /* 见各 type 定义 */ }
}
```

**约定**：
- `type` 命名空间：`audio.*`、`call.*`、`translate.*`、`whisper.*`、`rt2.*`、`escalate.*`、`error.*`、`system.*`
- 二进制音频帧（PCM16）也走 **JSON + base64**（payload.audio 字段），不开 binary frame，便于在浏览器 DevTools 直接观察
- 服务端到客户端的所有 `*.delta` 类型消息可能**乱序到达**，前端按 `seq` 排序
- 心跳：客户端每 15s 发 `system.ping`，服务端立即回 `system.pong`；超时 30s 关闭连接

### 11.1.2 错误码

```jsonc
{
  "type": "error.raised",
  "payload": {
    "code": "E_FOUNDRY_DISCONNECT",
    "message": "Upstream Realtime API disconnected",
    "retriable": true,
    "details": { /* 自由结构 */ }
  }
}
```

| code | retriable | 含义 |
|------|-----------|------|
| `E_AUTH_FAILED` | false | API key/MI token 失败 |
| `E_FOUNDRY_DISCONNECT` | true | 上游 Realtime API 断开 |
| `E_AUDIO_FORMAT` | false | PCM 格式不符（非 16-bit / 非 24kHz） |
| `E_AUDIO_TOO_LARGE` | true | 单帧 > 64 KB |
| `E_ESCALATE_NO_CONTEXT` | false | 升级时缺少 order_id 或对话摘要 |
| `E_TOOL_TIMEOUT` | true | 工具调用超时（默认 5s） |
| `E_TOOL_UNKNOWN` | false | 模型调用了未注册的工具 |
| `E_RATE_LIMIT` | true | Foundry 配额或并发达限 |
| `E_SESSION_EXPIRED` | false | 通话超过 `MAX_CALL_DURATION_SEC` |
| `E_INTERNAL` | false | 兜底未分类错误 |

### 11.1.3 音频帧规格

| 项 | 值 |
|----|----|
| 编码 | PCM16 little-endian |
| 采样率 | 24 000 Hz |
| 声道 | mono |
| 帧时长 | **20 ms**（480 samples = 960 bytes） |
| 传输 | base64 字符串放在 `payload.audio` |
| 单帧最大 | 64 KB（base64 后约 87 KB；超过即拒收并报 `E_AUDIO_TOO_LARGE`） |

---

## 11.2 `/ws/customer`

> 客户浏览器 ↔ 后端。承载：客户中文音频上行；英文 → 中文译音 + 中文原文字幕 下行。
> 后端为本通道在 Foundry 上同时维护两个 Realtime session：translate（英→中、中→英 反向也走这条）+ whisper（中文转写）。

### 11.2.1 Inbound（client → server）

| type | payload | 触发时机 |
|------|---------|----------|
| `call.start` | `{ role: "customer", lang: "zh-CN", target_lang: "en-US" }` | 客户点击 Start Call |
| `audio.frame` | `{ audio: "<base64-pcm16>", duration_ms: 20 }` | 麦克风每 20ms 一帧 |
| `audio.flush` | `{}` | 用户松开 push-to-talk 或前端 VAD 判断 end-of-utterance |
| `call.end` | `{ reason: "user_hangup" \| "timeout" \| "error" }` | 客户点击挂断 |
| `system.ping` | `{}` | 每 15s |

### 11.2.2 Outbound（server → client）

| type | payload | 来源 |
|------|---------|------|
| `call.started` | `{ call_id, voice: "alloy", started_at }` | 服务端确认建立 |
| `whisper.transcript.delta` | `{ text: "你好，我", is_final: false }` | whisper 流式增量原文 |
| `whisper.transcript.completed` | `{ text: "你好，我上周买的咖啡机收到时漏水，订单号 A12345。", utt_id: "u-1" }` | 一句结束 |
| `translate.text.delta` | `{ text: "Hello, the coffee machine...", direction: "agent_to_customer", is_final: false }` | 坐席英文 → 中文译文（给客户看） |
| `translate.audio.delta` | `{ audio: "<base64-pcm16>", direction: "agent_to_customer" }` | 中文译音播放 |
| `translate.audio.done` | `{ direction: "agent_to_customer" }` | 一段译音结束，前端 flush player |
| `call.ended` | `{ duration_ms, audit_url: "/audit/C-...jsonl" }` | 通话结束、合规文件写入完成 |
| `system.pong` | `{}` | 回 ping |
| `error.raised` | 见 §11.1.2 | 任意时刻 |

### 11.2.3 时序示例

```
C → S  call.start
S → C  call.started (call_id assigned)
C → S  audio.frame × N
S → C  whisper.transcript.delta × N   (客户自己说的话的原文)
S → C  whisper.transcript.completed
   ... (坐席开始说话)
S → C  translate.text.delta × N        (坐席英文译成中文)
S → C  translate.audio.delta × N
S → C  translate.audio.done
C → S  call.end
S → C  call.ended
```

---

## 11.3 `/ws/agent`

> 坐席浏览器 ↔ 后端。结构与 `/ws/customer` **对称**，多两个事件：
> - inbound：`escalate.request`（升级触发）
> - outbound：`escalate.acked`（升级确认）

### 11.3.1 Inbound

| type | payload | 触发 |
|------|---------|------|
| `call.start` | `{ role: "agent", lang: "en-US", target_lang: "zh-CN" }` | 坐席接听 |
| `audio.frame` | 同 §11.2.1 | |
| `audio.flush` | `{}` | |
| `escalate.request` | `{ order_id?: "A12345", note?: "customer asking for tariff waiver" }` | 坐席点击 Escalate |
| `call.end` | 同 §11.2.1 | |
| `system.ping` | `{}` | |

### 11.3.2 Outbound

| type | payload | 来源 |
|------|---------|------|
| `call.started` | 同 §11.2.2 | |
| `whisper.transcript.delta` / `.completed` | 同上，但是坐席自己说英文的原文 | whisper |
| `translate.text.delta` | `{ text, direction: "customer_to_agent", is_final }` | 客户中文译成英文（给坐席看） |
| `translate.audio.delta` / `.done` | `direction: "customer_to_agent"` | 英文译音 |
| `escalate.acked` | `{ assist_ws_url: "/ws/assist?call_id=...", context_summary: "..." }` | 升级被后端接受 |
| `call.ended` | 同上 | |
| `system.pong` | `{}` | |
| `error.raised` | | |

---

## 11.4 `/ws/assist`

> 坐席 Escalate 后才打开。承载：rt-2 的推理 trace + 工具调用 + 最终音频回复。
> 后端为本通道在 Foundry 上维护一个 `gpt-realtime-2` session，`reasoning.effort` 默认 high。

### 11.4.1 Inbound

| type | payload | 触发 |
|------|---------|------|
| `assist.start` | `{ call_id, context_summary: string, order_id?: string, reasoning_effort?: "minimal"\|"low"\|"medium"\|"high" }` | 坐席升级后由前端打开 WS 即发送 |
| `assist.user_text` | `{ text: "再确认一下保险是否覆盖关税" }` | 坐席补充文字提问（可选） |
| `assist.audio.frame` | `{ audio, duration_ms }` | 坐席用语音追问（可选，v0.2） |
| `assist.end` | `{ reason }` | 通话结束或主动关闭 |
| `system.ping` | `{}` | |

### 11.4.2 Outbound

| type | payload | 来源 |
|------|---------|------|
| `assist.started` | `{ session_id, model: "gpt-realtime-2", reasoning_effort: "high" }` | 服务端 ack |
| `rt2.reasoning.delta` | `{ text: "用户诉求是退换 + 关税豁免...", step: 1 }` | rt-2 流式思考链 |
| `rt2.reasoning.completed` | `{ summary: "决定先查订单状态" }` | 一段推理结束 |
| `rt2.tool_call` | `{ call_id: "tc-1", name: "get_order", arguments: { order_id: "A12345" } }` | rt-2 发起工具调用 |
| `rt2.tool_result` | `{ call_id: "tc-1", name: "get_order", result: { /* ... */ }, duration_ms: 230, ok: true }` | 后端执行后回写给前端 |
| `rt2.text.delta` | `{ text: "根据订单 A12345..." }` | 最终回复文本流 |
| `rt2.audio.delta` | `{ audio: "<base64-pcm16>" }` | 最终回复音频流 |
| `rt2.audio.done` | `{}` | 音频段结束 |
| `rt2.done` | `{ total_tokens, reasoning_tokens, tool_calls_count }` | 整个 turn 完成 |
| `system.pong` | `{}` | |
| `error.raised` | | |

### 11.4.3 时序示例

```
C → S  assist.start { call_id, context_summary, order_id }
S → C  assist.started
S → C  rt2.reasoning.delta × N       (思考链流式)
S → C  rt2.tool_call { get_order }
   ... 后端执行
S → C  rt2.tool_result { get_order, ok }
S → C  rt2.reasoning.delta × N
S → C  rt2.tool_call { check_tariff }
S → C  rt2.tool_result { check_tariff, ok }
S → C  rt2.tool_call { check_insurance }
S → C  rt2.tool_result { check_insurance, ok }
S → C  rt2.text.delta × N
S → C  rt2.audio.delta × N
S → C  rt2.audio.done
S → C  rt2.done { tool_calls_count: 3 }
```

---

## 11.5 Python TypedDict 全集（可直接复制到 `backend/app/realtime/protocol.py`）

```python
from __future__ import annotations
from typing import Literal, NotRequired, TypedDict

# === Envelope ===

class Envelope(TypedDict):
    v: Literal[1]
    type: str
    ts: int
    call_id: str
    seq: int
    payload: dict

# === /ws/customer & /ws/agent shared ===

class CallStartPayload(TypedDict):
    role: Literal["customer", "agent"]
    lang: str
    target_lang: str

class AudioFramePayload(TypedDict):
    audio: str               # base64 PCM16
    duration_ms: int

class CallEndPayload(TypedDict):
    reason: Literal["user_hangup", "timeout", "error"]

class CallStartedPayload(TypedDict):
    call_id: str
    voice: str
    started_at: int

class WhisperTranscriptDeltaPayload(TypedDict):
    text: str
    is_final: bool

class WhisperTranscriptCompletedPayload(TypedDict):
    text: str
    utt_id: str

TranslateDirection = Literal["customer_to_agent", "agent_to_customer"]

class TranslateTextDeltaPayload(TypedDict):
    text: str
    direction: TranslateDirection
    is_final: bool

class TranslateAudioDeltaPayload(TypedDict):
    audio: str
    direction: TranslateDirection

class TranslateAudioDonePayload(TypedDict):
    direction: TranslateDirection

class CallEndedPayload(TypedDict):
    duration_ms: int
    audit_url: str

# === /ws/agent specific ===

class EscalateRequestPayload(TypedDict, total=False):
    order_id: str
    note: str

class EscalateAckedPayload(TypedDict):
    assist_ws_url: str
    context_summary: str

# === /ws/assist ===

ReasoningEffort = Literal["minimal", "low", "medium", "high"]

class AssistStartPayload(TypedDict, total=False):
    call_id: str
    context_summary: str
    order_id: str
    reasoning_effort: ReasoningEffort

class AssistStartedPayload(TypedDict):
    session_id: str
    model: str
    reasoning_effort: ReasoningEffort

class Rt2ReasoningDeltaPayload(TypedDict):
    text: str
    step: int

class Rt2ToolCallPayload(TypedDict):
    call_id: str
    name: str
    arguments: dict

class Rt2ToolResultPayload(TypedDict):
    call_id: str
    name: str
    result: dict
    duration_ms: int
    ok: bool

class Rt2DonePayload(TypedDict):
    total_tokens: int
    reasoning_tokens: int
    tool_calls_count: int

# === Error ===

class ErrorPayload(TypedDict, total=False):
    code: str
    message: str
    retriable: bool
    details: dict
```

---

## 11.6 TypeScript 类型全集（可直接复制到 `frontend/lib/types.ts`）

```typescript
export type ProtocolVersion = 1;

export interface Envelope<T = unknown> {
  v: ProtocolVersion;
  type: string;
  ts: number;
  call_id: string;
  seq: number;
  payload: T;
}

export type Role = "customer" | "agent";
export type TranslateDirection = "customer_to_agent" | "agent_to_customer";
export type ReasoningEffort = "minimal" | "low" | "medium" | "high";

// --- Customer / Agent shared ---
export interface CallStartPayload {
  role: Role;
  lang: string;
  target_lang: string;
}
export interface AudioFramePayload {
  audio: string;
  duration_ms: number;
}
export interface CallEndPayload {
  reason: "user_hangup" | "timeout" | "error";
}
export interface CallStartedPayload {
  call_id: string;
  voice: string;
  started_at: number;
}
export interface WhisperTranscriptDeltaPayload {
  text: string;
  is_final: boolean;
}
export interface WhisperTranscriptCompletedPayload {
  text: string;
  utt_id: string;
}
export interface TranslateTextDeltaPayload {
  text: string;
  direction: TranslateDirection;
  is_final: boolean;
}
export interface TranslateAudioDeltaPayload {
  audio: string;
  direction: TranslateDirection;
}
export interface CallEndedPayload {
  duration_ms: number;
  audit_url: string;
}

// --- Agent only ---
export interface EscalateRequestPayload {
  order_id?: string;
  note?: string;
}
export interface EscalateAckedPayload {
  assist_ws_url: string;
  context_summary: string;
}

// --- Assist ---
export interface AssistStartPayload {
  call_id: string;
  context_summary: string;
  order_id?: string;
  reasoning_effort?: ReasoningEffort;
}
export interface AssistStartedPayload {
  session_id: string;
  model: string;
  reasoning_effort: ReasoningEffort;
}
export interface Rt2ReasoningDeltaPayload {
  text: string;
  step: number;
}
export interface Rt2ToolCallPayload {
  call_id: string;
  name: string;
  arguments: Record<string, unknown>;
}
export interface Rt2ToolResultPayload {
  call_id: string;
  name: string;
  result: Record<string, unknown>;
  duration_ms: number;
  ok: boolean;
}
export interface Rt2DonePayload {
  total_tokens: number;
  reasoning_tokens: number;
  tool_calls_count: number;
}

// --- Error ---
export interface ErrorPayload {
  code: string;
  message: string;
  retriable: boolean;
  details?: Record<string, unknown>;
}
```

---

## 11.7 协议演进规则

1. **新增字段**（向后兼容）：不升 `v`，但需在本文件 changelog 备注
2. **删除/重命名字段**（破坏性）：必须升 `v`，并在 backend 兼容 N 与 N-1 至少 1 个 release
3. **新增 type**：不升 `v`，但客户端遇到未知 type 必须**忽略**而不是报错
4. **payload 字段顺序无关**，序列化用 orjson（后端）/ JSON.stringify（前端）默认顺序

---

## 11.8 验收（供 issue 引用）

- [ ] `backend/app/realtime/protocol.py` 含本文 §11.5 全部 TypedDict
- [ ] `frontend/lib/types.ts` 含本文 §11.6 全部 interface
- [ ] WS gateway 三端点对未知 `type` 的入站消息**忽略并日志 WARN**，不断连
- [ ] 错误统一走 `error.raised`，前端有全局 toast 渲染
- [ ] 心跳超时 30s 关闭连接（单测覆盖）
- [ ] 单帧 > 64KB 返回 `E_AUDIO_TOO_LARGE` 并丢弃（单测覆盖）

---

下一篇：[12-realtime-session-config.md](./12-realtime-session-config.md) 看每个 Foundry session 的完整 `session.update` payload。
