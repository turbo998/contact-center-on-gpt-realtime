# 12 · Realtime Session Config（三模型 session.update 完整 payload）

> 本文给出三个 Foundry Realtime session 的**完整 `session.update` JSON**，可直接粘贴到 smoke-test 脚本或 `backend/app/realtime/*.py` 中。
> 协议形态参考 `openai-python>=1.55` + Azure OpenAI `2025-04-01-preview`。如官方升级，以官方为准。

---

## 12.1 通用：连接与认证

### Endpoint（Azure）

```
wss://{AZURE_OPENAI_ENDPOINT_HOST}/openai/realtime?api-version=2025-04-01-preview&deployment={DEPLOYMENT_NAME}
```

- `AZURE_OPENAI_ENDPOINT_HOST` 来自 `.env`，形如 `your-foundry.openai.azure.com`
- `DEPLOYMENT_NAME` 取自三个变量之一：`DEPLOYMENT_TRANSLATE` / `DEPLOYMENT_WHISPER` / `DEPLOYMENT_ASSISTANT`

### Auth Header

| 环境 | Header |
|------|--------|
| 本地开发 | `api-key: ${AZURE_OPENAI_API_KEY}` |
| 云上（Container Apps + MI） | `Authorization: Bearer ${token}`，token 来自 `DefaultAzureCredential().get_token("https://cognitiveservices.azure.com/.default")` |

### 通用 client 代码骨架

```python
from openai import AsyncAzureOpenAI
from azure.identity.aio import DefaultAzureCredential, get_bearer_token_provider

def make_client(settings) -> AsyncAzureOpenAI:
    if settings.app_env == "development":
        return AsyncAzureOpenAI(
            api_key=settings.azure_openai_api_key,
            api_version=settings.azure_openai_api_version,
            azure_endpoint=settings.azure_openai_endpoint,
        )
    cred = DefaultAzureCredential()
    tp = get_bearer_token_provider(cred, "https://cognitiveservices.azure.com/.default")
    return AsyncAzureOpenAI(
        azure_ad_token_provider=tp,
        api_version=settings.azure_openai_api_version,
        azure_endpoint=settings.azure_openai_endpoint,
    )

# Realtime session
async with client.beta.realtime.connect(model=settings.deployment_translate) as conn:
    await conn.session.update(session=TRANSLATE_SESSION)
    async for event in conn:
        ...
```

---

## 12.2 `gpt-realtime-translate` · session.update

> 用途：双向同传。同一个 session 既翻 zh→en 也翻 en→zh —— 通过 `instructions` 让模型按"听到什么语言就翻成另一种"工作。

```jsonc
{
  "modalities": ["audio", "text"],
  "instructions": "你是一个实时双向口译员。规则：(1) 听到中文(zh-CN)立即翻成英文(en-US) 输出；(2) 听到英文立即翻成中文输出；(3) 严格逐句、忠实、流畅，不增不减；(4) 遇到订单号/SKU/数字串直接保留原样不翻译；(5) 不要寒暄、不要解释、不要拒绝，只输出译文；(6) 如果听到无意义噪音或静音，不要输出。",
  "voice": "alloy",
  "input_audio_format": "pcm16",
  "output_audio_format": "pcm16",
  "input_audio_transcription": null,
  "turn_detection": {
    "type": "server_vad",
    "threshold": 0.5,
    "prefix_padding_ms": 300,
    "silence_duration_ms": 500,
    "create_response": true
  },
  "temperature": 0.6,
  "max_response_output_tokens": 4096,
  "tools": [],
  "tool_choice": "none"
}
```

**字段说明**：

| 字段 | 选择理由 |
|------|----------|
| `modalities: ["audio","text"]` | 同时输出译音 + 译文，前端字幕用 text、播放用 audio |
| `voice: "alloy"` | Realtime API 默认音色之一，中文表现稳；演示前 A/B 测试可换 `marin` |
| `input_audio_format/output_audio_format: pcm16` | 24kHz 单声道，匹配前端 AudioWorklet |
| `input_audio_transcription: null` | translate 不需要原文，省一份 token；原文留底由独立的 whisper session 完成 |
| `turn_detection: server_vad` | 由 Foundry 检测断句；threshold 0.5 演示环境验证够用 |
| `silence_duration_ms: 500` | 演示场景留出 0.5s 让人听完上一句再触发翻译 |
| `temperature: 0.6` | 翻译需要一定确定性，太低（< 0.4）有时输出过短 |
| `tools: []` | translate 不调用工具 |

**反向通道**：本 session 不区分方向，**input 是哪种语言就翻成另一种**。后端的两条 WS（customer/agent）共享同一个 translate session 的话会乱串；**建议每个角色单独一个 translate session**（设计 D1 已经定）。

---

## 12.3 `gpt-realtime-whisper` · session.update

> 用途：原文流式转写，**只出文字**，用于合规留底。

```jsonc
{
  "modalities": ["text"],
  "instructions": "你是流式语音转写引擎。规则：(1) 严格按听到的内容转写，不要翻译、不要润色、不要总结；(2) 中文输出简体，英文输出原文；(3) 标点按自然停顿；(4) 数字/订单号保留原始形式；(5) 不要输出无意义内容（如咳嗽、纯静音）。",
  "voice": null,
  "input_audio_format": "pcm16",
  "output_audio_format": null,
  "input_audio_transcription": {
    "model": "whisper-1",
    "language": null,
    "prompt": "客服售后 订单号 关税 保险 退货 换新 物流 SKU"
  },
  "turn_detection": {
    "type": "server_vad",
    "threshold": 0.5,
    "prefix_padding_ms": 300,
    "silence_duration_ms": 700,
    "create_response": false
  },
  "temperature": 0.0,
  "tools": [],
  "tool_choice": "none"
}
```

**字段说明**：

| 字段 | 选择理由 |
|------|----------|
| `modalities: ["text"]` | 不需要任何音频输出 |
| `output_audio_format: null` | 显式关闭，节省带宽 |
| `input_audio_transcription.model` | 沿用 whisper-1 系语义；如部署名不同（如 `gpt-realtime-whisper`），改成实际 deployment |
| `input_audio_transcription.language: null` | 由模型自动检测（中英混说也能识别） |
| `input_audio_transcription.prompt` | 注入业务术语词表，提升订单号 / 关税等术语识别率 |
| `turn_detection.create_response: false` | whisper 只转写不"回复"，关闭 response 生成节省调用 |
| `silence_duration_ms: 700` | 比 translate 略长，给一句完整结束更明显的分隔 |
| `temperature: 0.0` | 转写要确定性最高 |

### 关键事件流

| Foundry 事件 | 后端动作 |
|--------------|----------|
| `conversation.item.input_audio_transcription.delta` | 转成 `whisper.transcript.delta` 推给前端 |
| `conversation.item.input_audio_transcription.completed` | 转成 `whisper.transcript.completed`，**同时写 audit JSONL** |
| `error` | 转成 `error.raised` (code=`E_FOUNDRY_DISCONNECT` if disconnect) |

---

## 12.4 `gpt-realtime-2` · session.update

> 用途：复杂推理 + 工具调用 + 给客户的最终方案（中文音频）。

```jsonc
{
  "modalities": ["audio", "text"],
  "instructions": "你是跨境电商客服 AI 助理。你的客户是英国总部的一线坐席，他们刚把一通复杂的中文客户来电升级给你处理。\n\n工作规则：\n1. 收到 escalate 时，上下文会包含：最近 30 秒对话摘要 + 客户订单号 + 客户诉求要点。\n2. 你**必须**先调用 get_order(order_id) 拿到订单详情。\n3. 如果涉及关税/进口费用，**必须**调用 check_tariff(from_country, to_country, sku)。\n4. 如果客户提到保险或希望免运费，**必须**调用 check_insurance(policy_id)。\n5. 工具调用完成后，给出**一个明确的方案**（A/B 二选一即可），用**简体中文**回复（要让客户听得懂），语速适中。\n6. 回复结构：诉求确认 → 方案 → 关键金额/时间 → 请客户确认。\n7. 总字数控制在 80–150 字，避免冗长。\n8. 推理过程（reasoning）会被坐席看到，所以思考链请用中文、要点式表述。\n9. 不要承诺超出工具返回结果之外的内容（不要幻觉编造金额、政策）。\n10. 如果工具返回 not_found 或失败，明确告诉客户'需要人工进一步核实'，不要瞎编。",
  "voice": "marin",
  "input_audio_format": "pcm16",
  "output_audio_format": "pcm16",
  "input_audio_transcription": {
    "model": "whisper-1",
    "language": "zh"
  },
  "turn_detection": {
    "type": "server_vad",
    "threshold": 0.5,
    "prefix_padding_ms": 300,
    "silence_duration_ms": 600,
    "create_response": true
  },
  "temperature": 0.7,
  "max_response_output_tokens": 1024,
  "reasoning": {
    "effort": "high"
  },
  "tools": [
    {
      "type": "function",
      "name": "get_order",
      "description": "查询订单详情。返回订单的 sku、收货国、发货国、状态、金额。",
      "parameters": {
        "type": "object",
        "properties": {
          "order_id": { "type": "string", "description": "订单号，例如 A12345" }
        },
        "required": ["order_id"],
        "additionalProperties": false
      }
    },
    {
      "type": "function",
      "name": "check_tariff",
      "description": "查询某 SKU 从一个国家到另一个国家的关税金额（GBP）。",
      "parameters": {
        "type": "object",
        "properties": {
          "from_country": { "type": "string", "description": "ISO 3166-1 alpha-2 国家码，如 CN" },
          "to_country":   { "type": "string", "description": "ISO 3166-1 alpha-2 国家码，如 GB" },
          "sku":          { "type": "string", "description": "商品 SKU，如 COFFEE-MAKER" }
        },
        "required": ["from_country", "to_country", "sku"],
        "additionalProperties": false
      }
    },
    {
      "type": "function",
      "name": "check_insurance",
      "description": "查询保险单是否覆盖跨境运费或关税。",
      "parameters": {
        "type": "object",
        "properties": {
          "policy_id": { "type": "string", "description": "保险单号，如 INS-7788" }
        },
        "required": ["policy_id"],
        "additionalProperties": false
      }
    }
  ],
  "tool_choice": "auto"
}
```

**字段说明**：

| 字段 | 选择理由 |
|------|----------|
| `reasoning.effort: high` | 演示重点是"会推理"；非升级时可下调到 `medium` 省成本 |
| `voice: marin` | 中文女声，演示效果优于 alloy（A/B 实测） |
| `max_response_output_tokens: 1024` | 限制最终方案长度，避免冗长 |
| `tool_choice: "auto"` | 让模型自己决定调用顺序；prompt 已明确顺序要求 |
| `temperature: 0.7` | 比 translate 略高，方案表达需要一定自然性 |
| `input_audio_transcription.language: "zh"` | rt-2 收到的是经过翻译的客户中文上下文，固定 zh |

### Escalate 时如何注入上下文

后端在 `assist.start` 接收后，立即对 rt-2 发：

```python
await conn.session.update(session=RT2_SESSION)
# 注入对话历史
await conn.conversation.item.create(item={
    "type": "message",
    "role": "system",
    "content": [{
        "type": "input_text",
        "text": f"【最近对话摘要】\n{context_summary}\n\n【订单号】{order_id}\n\n【坐席备注】{note or '（无）'}\n\n请按系统提示流程开始处理。"
    }]
})
await conn.response.create()
```

---

## 12.5 事件流对照表

| 上游 Foundry 事件 | translate 用到 | whisper 用到 | rt-2 用到 | 下行客户端事件 |
|-------------------|---|---|---|----------------|
| `session.created` | ✓ | ✓ | ✓ | `call.started` / `assist.started` |
| `session.updated` | ✓ | ✓ | ✓ | （后端确认日志） |
| `input_audio_buffer.committed` | ✓ | ✓ | — | （内部 trace） |
| `conversation.item.input_audio_transcription.delta` | — | ✓ | — | `whisper.transcript.delta` |
| `conversation.item.input_audio_transcription.completed` | — | ✓ | — | `whisper.transcript.completed` + audit |
| `response.created` | ✓ | — | ✓ | — |
| `response.text.delta` | ✓ | — | ✓ | `translate.text.delta` / `rt2.text.delta` |
| `response.audio.delta` | ✓ | — | ✓ | `translate.audio.delta` / `rt2.audio.delta` |
| `response.audio.done` | ✓ | — | ✓ | `translate.audio.done` / `rt2.audio.done` |
| `response.audio_transcript.delta` | ✓ | — | ✓ | （合并入 `*.text.delta`） |
| `response.function_call_arguments.delta` | — | — | ✓ | `rt2.tool_call`（增量累积，args 完整后一次性 emit） |
| `response.function_call_arguments.done` | — | — | ✓ | 触发后端 dispatcher 执行工具 |
| `response.output_item.done` (with reasoning) | — | — | ✓ | `rt2.reasoning.delta` / `.completed` |
| `response.done` | ✓ | — | ✓ | `rt2.done` |
| `error` | ✓ | ✓ | ✓ | `error.raised` |

---

## 12.6 关键参数选择理由（FAQ）

**Q: 为什么 24kHz 而不是 16kHz？**
A: Realtime API 文档建议 24kHz；与 OpenAI TTS 输出采样率一致，避免重采样。24kHz mono PCM16 仅 48 kbps，对带宽无压力。

**Q: 为什么 `server_vad` 而不是 `none`（push-to-talk）？**
A: Demo 场景双向对话流畅性优先；push-to-talk 演示效果差。生产场景对回声敏感可换 `none` + 客户端 VAD。

**Q: 为什么 translate 不开 `input_audio_transcription`？**
A: translate 输出的是译文文本，不是原文转写。如果同时开转写会重复计费（输入音频会被同时送翻译 + 转写）。原文留底交给独立的 whisper session。

**Q: 为什么 rt-2 的 `tool_choice` 不强制成 "required"？**
A: 演示场景 prompt 已明确"必须先调用 get_order"。强制 `required` 会让所有 turn 都被迫调用工具，副作用是后续轮次也强行调用。

**Q: `silence_duration_ms` 三个模型为何不同？**
A: translate 要求快（500ms），whisper 要求边界清晰（700ms），rt-2 是 AI 主导的对话（600ms 折中）。

---

## 12.7 验收（供 issue 引用）

- [ ] 三个 smoke 脚本（`scripts/smoke-translate.py` / `smoke-whisper.py` / `smoke-rt2.py`）使用本文 §12.2/12.3/12.4 的 session 配置
- [ ] smoke-translate：中文 wav → 收到英文 audio + text；首 audio chunk 延迟 < 1s
- [ ] smoke-whisper：中文 wav → 收到流式中文 transcript；终态 transcript 与音频内容一致
- [ ] smoke-rt2：注入 escalate context（A12345）→ rt-2 至少调用 3 个工具 → 最终输出中文音频
- [ ] 后端 `app/realtime/*.py` 中 session 配置常量与本文一致（通过 grep 验证）

---

下一篇：[13-mock-data-and-tools.md](./13-mock-data-and-tools.md) 看三个 mock 工具的 schema、fixture 与编排。
