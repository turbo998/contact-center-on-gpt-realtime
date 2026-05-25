# 02 · Business Scenario

## 2.1 一句话场景

> **中国客户**（说中文）致电**英国跨境电商总部**（坐席说英文），就一笔咖啡机售后提出**复杂的、跨越关税与保险条款的诉求**。三款 GPT-realtime 模型协同完成整通通话。

## 2.2 角色定义

| 角色 | 语言 | 系统支持 |
|------|------|----------|
| **客户 Customer** | 简体中文 | 浏览器麦克风 → 听到中文译音 + 看到中文原文字幕 |
| **坐席 Agent** | English | 浏览器麦克风 → 听到英文译音 + 看到双语字幕 + 可点击 *Escalate* |
| **AI 助理 Assistant** | 中英任意 | 由坐席升级触发，`reasoning.effort=high`，能调用 mock CRM 工具 |

## 2.3 6 步业务脚本

> 完整通话约 60–90 秒，建议路演时控制在 90 秒以内。

| # | 时间线 | 角色发声内容 | 系统行为 | 演示要点 |
|---|--------|--------------|----------|----------|
| **1** | 0:00 | 客户（中）："你好，我上周买的咖啡机收到时漏水，订单号 A12345。" | • `translate` 即时译为英文语音推给坐席<br>• `whisper` **并行**生成中文原文字幕<br>• 两路结果在 UI 同步出现 | **三模型中两个并行工作** |
| **2** | 0:08 | 坐席（英）："Sorry to hear that. Let me check the order…" | `translate` 反向译为中文播给客户；中英文字幕双向滚动 | **双向同传** |
| **3** | 0:25 | 客户（中）："我希望退货换新，但关税和保险我不想自己出，能帮我想个方案吗？" | 坐席判断诉求复杂，点击 **Escalate to AI 按钮** | **业务升级时机** |
| **4** | 0:30 | — | • 后端把最近 30 秒对话摘要 + 订单上下文 push 给 `gpt-realtime-2`<br>• 设置 `reasoning.effort=high`<br>• realtime-2 调用 mock 工具：`get_order("A12345")` → `check_tariff("CN", "COFFEE-MAKER")` → `check_insurance("INS-7788")` | **推理 + 工具调用可视化** |
| **5** | 0:55 | AI 助理（中）："根据订单 A12345 和您的保险条款，建议方案 A：免费换新，关税由我方承担，预计 7 个工作日到货。如可接受请确认。" | UI 推理面板同步展示思考链 + 工具调用 trace | **可解释性** |
| **6** | 通话结束 | — | 一键导出 `audit-{call_id}.jsonl`，含：<br>• whisper 原文（合规要求）<br>• translate 双语对照<br>• realtime-2 推理 trace + 工具调用 | **合规留底闭环** |

## 2.4 UI Wireframe（三栏布局）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  Contact Center · Call #C-20260525-001 · ⏱ 00:42 · ● Live                   │
├─────────────────────────────┬─────────────────────────────┬─────────────────┤
│  CUSTOMER (zh-CN)           │  AGENT (en-US)              │  AI ASSIST      │
│  🎤 [Mic ON]                │  🎤 [Mic ON]                │  Status: Idle   │
│                             │                             │                 │
│  ──── 原文字幕 ────           │  ──── 字幕 ────              │  [ Escalate ]   │
│  你好，我上周买的             │  Hello, the coffee machine  │                 │
│  咖啡机收到时漏水…             │  I bought last week leaked  │  ─── 推理 trace ─│
│                             │  on arrival.                │  (待激活)        │
│  ──── 译文（来自坐席）────      │                             │                 │
│  抱歉听到这个消息…             │  ──── 译文（来自客户）────     │  ─── 工具调用 ───│
│                             │  Hello, the coffee…         │  (待激活)        │
│                             │                             │                 │
│  [ End Call ]               │  [ End Call ]   [Escalate]  │                 │
└─────────────────────────────┴─────────────────────────────┴─────────────────┘
```

升级后（第 4 步）：

```
│  AI ASSIST                  │
│  Status: 🟢 Active (rt-2)   │
│  reasoning.effort: high     │
│                             │
│  ─── 推理 trace ───          │
│  ▸ 用户诉求：退换 + 关税豁免 │
│  ▸ 调用 get_order(A12345)   │
│  ▸ 收货国: GB, 原产: CN     │
│  ▸ 调用 check_tariff(...)   │
│  ▸ 关税: £18.50             │
│  ▸ 调用 check_insurance(...) │
│  ▸ 保险覆盖运费             │
│  ▸ 推荐方案 A                │
│                             │
│  ─── 工具调用 ───            │
│  get_order ✓ 0.2s           │
│  check_tariff ✓ 0.3s        │
│  check_insurance ✓ 0.2s     │
```

## 2.5 路演口径

### 30 秒电梯版

> "这是一个跨境客服 Demo —— 中国客户用中文打电话，英国坐席听到的是英文。我们用三个 GPT-realtime 模型协作：translate 做双向同传，whisper 同时把中文原文存下来做合规，遇到复杂问题坐席一键升级，realtime-2 会调用 CRM 工具做多步推理给方案。**三模型同时在线**，全程音频流式处理，**首音延迟控制在 1.5 秒内**。"

### 3 分钟标准版

1. **开场（30s）** —— "为什么要做这个 Demo"：三模型业务价值（[01-overview](./01-overview.md)）
2. **演示（90s）** —— 现场跑通 6 步脚本
3. **架构（30s）** —— 切到 [03-architecture](./03-architecture.md) 的图，强调三 WS 通道隔离
4. **价值（30s）** —— 合规闭环 + 可解释 AI + 工程成本（一份 FastAPI + 一份 Next.js）

## 2.6 备选场景

如果首选无法演示（网络/设备故障），用预录音频版本：

- 客户音频：`assets/recordings/customer-zh.wav`（约 30 秒，3 句话）
- 坐席音频：`assets/recordings/agent-en.wav`（约 20 秒，2 句话）

预录路径下 Escalate 仍走真实 realtime-2，保证推理部分仍是 live。

---

下一步：[03-architecture.md](./03-architecture.md) 看系统如何把这些串起来。
