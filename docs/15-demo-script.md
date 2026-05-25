# 15. 现场 Demo 脚本与运行手册（Live Demo Runbook）

> 本文是讲师现场演示的"剧本 + 检查清单 + 应急预案"。目标：8 分钟内、零卡顿、零观众察觉的 bug，把"一通跨境客服电话"完整跑完，并清晰回扣三个新模型（`gpt-realtime`、`gpt-4o-transcribe / whisper`、`gpt-4o-mini-translate`）的能力点。
>
> 适用场景：Workshop 现场（投屏 + 麦克风）、线上直播、录播视频。
>
> 阅读对象：主讲人、副讲（操作员）、录制 / 直播运维。

---

## 15.1 Pre-demo Checklist（开场前 30 分钟必做）

下面这张表是上台前的"飞行前检查"，每一项必须由"操作员"逐条打勾，主讲人复核签字。

| # | 检查项 | 通过标准 | 负责人 |
|---|---|---|---|
| 1 | 演示笔记本 | 电量 ≥ 80%，已插电源；关闭系统更新、IDE 自动索引、Slack / 微信 / 邮件桌面通知 | 操作员 |
| 2 | 主网络 | 会场 Wi-Fi 可访问 `*.azurecontainerapps.io` 与 `*.openai.azure.com`，`ping` < 80ms | 操作员 |
| 3 | 备份网络 | 手机热点已开机并完成一次成功握手；笔记本 Wi-Fi 列表已置顶 | 操作员 |
| 4 | 浏览器标签 | 预开 3 个 tab：① 坐席端 UI ② Azure Portal（指向 Container App 监控） ③ `audit.jsonl` tail 页面；浏览器缩放 110%，开发者工具关闭 | 主讲人 |
| 5 | 声音 | 系统输出音量固定在 **70%**；会场扩声听一遍中文 / 英文 TTS 各一句，确认无爆音、无延迟回授 | 操作员 |
| 6 | `fixtures.json` | `scripts/fixtures/fixtures.json` 含 `A12345` 订单、`INS-7788` 保单、`COFFEE-MAKER` 关税三条记录，最后修改时间 = 今日 | 操作员 |
| 7 | 环境变量 | `.env.demo` 已 `source`：`AZURE_OPENAI_ENDPOINT` / `AZURE_OPENAI_API_KEY` / `REALTIME_DEPLOYMENT` / `TRANSLATE_DEPLOYMENT` / `WHISPER_DEPLOYMENT` / `AUDIT_LOG_PATH` 均非空 | 操作员 |
| 8 | 音频环路 | 若无真人麦或现场嘈杂：启用 BlackHole / VB-Cable 把 WAV 注入到浏览器输入设备；`系统设置 → 声音 → 输入` 已切到虚拟设备 | 操作员 |
| 9 | 预录 WAV | `scripts/audio-samples/` 下存在：`01-greeting-zh.wav`、`02-refund-zh.wav`、`03-confirm-zh.wav`、`04-agent-sorry-en.wav`，采样率 24kHz / 16bit / 单声道 | 操作员 |
| 10 | 健康检查 | `curl https://<app>.azurecontainerapps.io/healthz` 返回 `{"status":"ok"}` 且 `models: 3/3` | 主讲人 |
| 11 | 本地兜底 | `docker compose -f compose.demo.yml up -d` 已起，`http://localhost:3000/healthz` 200 | 操作员 |
| 12 | 录屏软件 | OBS 已加载 `demo-scene.json`，磁盘剩余 ≥ 20GB | 录制 |

> 经验：第 5、第 8 两条最容易翻车。**永远不要相信现场麦克风**，宁可一开始就走预录 WAV。

---

## 15.2 演示环境（Demo Environment）

- **主环境（云端 / 推荐）**
  - URL：`https://<app>.azurecontainerapps.io`
  - 区域：`eastus2`（与 `gpt-realtime` 部署同区，端到端 RTT < 250ms）
  - 副本数：固定 2（关闭 KEDA 自动伸缩，避免 demo 时冷启动）
  - 模型部署：
    - `gpt-realtime` → deployment `rt-main`，备份 `rt-backup`
    - `gpt-4o-mini-translate` → deployment `tr-main`
    - `whisper`（或 `gpt-4o-transcribe`） → deployment `asr-main`

- **本地兜底（Local Fallback）**
  - URL：`http://localhost:3000`
  - 启动：`pnpm demo:local` 或 `docker compose -f compose.demo.yml up -d`
  - 与云端共用同一份 `.env.demo`，工具调用走真实 Azure OpenAI，仅前端 + 编排层在本地

- **切换策略**：浏览器地址栏永远预填云端 URL；一旦云端连续 2 次 5xx 或 RTT > 1s，操作员按 `Ctrl+L`，粘贴本地 URL 回车切换，**不要在台上做 DNS 解释**。

---

## 15.3 Stage Layout（屏幕布局建议）

### 主屏：三栏式（强烈推荐 16:9 → 1920×1080）

```
┌──────────────────┬──────────────────┬──────────────────┐
│  Customer Pane   │   Agent Pane     │   AI Assist Pane │
│  （客户视角）     │   （坐席视角）    │   （AI 推理）     │
│                  │                  │                  │
│ • 中文原文       │ • 英文译文       │ • Reasoning chain│
│ • 中文译音播放    │ • 英文 ASR       │ • Tool calls     │
│ • 状态：通话中    │ • Escalate 按钮  │ • 最终方案音频   │
└──────────────────┴──────────────────┴──────────────────┘
```

- 每栏宽度均分 33.3%，顶部统一 48px 状态条（显示当前模型 + 延迟）。
- 字号 ≥ 18px，深色背景 + 高对比度字幕，后排观众也能看清。
- 左右两栏的字幕滚动方向**相反**（客户从下往上、坐席从上往下），便于观众一眼区分。

### 副屏（可选）

- 1080p 或更高，单独投放"AI Assist Pane 放大版"：把 reasoning chain 和 tool-call JSON 展开到全屏。
- 若没有副屏，Step 5 时主讲人手动按 `F` 全屏 AssistPane 5 秒再切回。

---

## 15.4 Golden Path：7 步金路径（总时长 ≤ 8 分钟）

> 时间戳是"理想线"，允许 ±15 秒。操作员手腕戴秒表，每步切换时给主讲人一个**眼神**而不是出声。

### Step 1 — 开场（0:00 – 0:30，30 秒）

- **动作**：主讲人站定，背对屏幕半侧身，右手指向三栏。
- **台词**：见 §15.5 Step 1。
- **屏幕**：空通话面板，仅显示 "Ready"。
- **关键点**：一句话点题——"一通跨境客服电话，串联 3 个新模型"。

### Step 2 — 客户中文开口（0:30 – 1:30，60 秒）

- **动作**：操作员点击 Customer Pane 的 "Start Call"，注入 `01-greeting-zh.wav` 或现场说：
  > "你好，我上周买的咖啡机收到时漏水，订单号 A12345。"
- **屏幕预期**：
  - Customer Pane：中文原文逐字浮现（whisper / `gpt-4o-transcribe`）
  - Agent Pane：英文译文几乎同时出现（`gpt-4o-mini-translate`），延迟 < 800ms
- **主讲人**：右手依次指 Customer Pane → Agent Pane，强调"**同传**"。

### Step 3 — 坐席英文回复（1:30 – 2:00，30 秒）

- **动作**：副讲（坐席）对着麦克风用英文说：
  > "I am sorry to hear that. Let me check your order."
- **屏幕预期**：
  - Agent Pane：英文 ASR
  - Customer Pane：中文 TTS 朗读译文（注意：是**译音**，不是原音）
- **关键点**：反向链路也通——translate 是双向的。

### Step 4 — 客户升级诉求 + 坐席点 Escalate（2:00 – 2:30，30 秒）

- **动作**：注入 `02-refund-zh.wav`：
  > "我想退换，并希望免运费。"
- **副讲**：在英文译文出现后 2 秒内，点击 Agent Pane 的 **Escalate** 按钮。
- **屏幕预期**：AI Assist Pane 立刻从灰底变蓝底，标题出现 "Reasoning…"。
- **主讲人**：用手指**啪**地一下指向 AssistPane，"看，AI 接管了"。

### Step 5 — AI Assist 推理 + 工具链（2:30 – 6:00，约 3.5 分钟）

这是全场高光，**最值得放慢节奏**。依次出现：

1. **Reasoning chain**（gpt-realtime 的可见思维链，约 5–8 行）
2. **Tool call #1**：`get_order(order_id="A12345")` → 返回购买时间、SKU、金额
3. **Tool call #2**：`check_tariff(origin="CN", dest="GB", sku="COFFEE-MAKER")` → 返回关税率与是否含运
4. **Tool call #3**：`check_insurance(policy_id="INS-7788")` → 返回是否覆盖运损
5. **最终方案**：中文 TTS 播放一段约 25 秒的解决方案音频（含退换流程 + 免运费承诺 + 时效）

- **主讲人节奏**：每个 tool call 出现时停顿 2 秒，念出函数名与关键参数，**不要念 JSON**。
- **观众视线**：副屏放大版此时打开最有效。

### Step 6 — 坐席复述 + 客户确认（6:00 – 6:30，30 秒）

- **副讲**：用英文把 AI 方案复述一遍（一句话即可，例如 "We will arrange a free-shipping replacement, ETA 5 business days."）。
- **客户**：注入 `03-confirm-zh.wav`：
  > "好的，谢谢，就这样办。"
- **屏幕预期**：两栏同步出现译文，AssistPane 状态变为 "Closed"。

### Step 7 — 挂断 + Audit 留底（6:30 – 7:30，60 秒）

- **动作**：副讲点 "End Call"；操作员在第三个浏览器 tab 打开 `audit.jsonl` tail 视图。
- **屏幕预期**：JSONL 中可逐条看到：
  - `transcript.zh.original`
  - `transcript.en.translated`
  - `reasoning.steps[]`
  - `tool_calls[]`（3 条）
  - `final_response.audio_url`
- **主讲人**：滚动到底，强调"**每一句原文、每一次推理、每一次工具调用，全留底**"。

剩余 30 秒缓冲，用于过渡到 Q&A。

---

## 15.5 旁白逐字稿（可直接照念）

> 全部为中文，节奏放慢，每句之间留 0.5 秒。

**Step 1（开场）**
> "各位老师好。接下来这 8 分钟，我们用一通真实的跨境客服电话，把 Azure OpenAI 最近上线的三个新模型——`gpt-realtime`、`gpt-4o-transcribe`、`gpt-4o-mini-translate`——一次性串起来。请大家看屏幕。"

**Step 2（客户开口）**
> "客户是中国买家，说的是中文。大家看左边——这是 `gpt-4o-transcribe` 的实时识别，逐字出。**几乎同时**，中间这栏出现了英文译文，这是 `gpt-4o-mini-translate`，端到端不到一秒。"

**Step 3（坐席回复）**
> "坐席只会英文，他说 'I am sorry, let me check'。注意左边客户面板——中文译音直接放出来了。**双向同传**，坐席和客户全程不用学对方的语言。"

**Step 4（升级）**
> "客户提了两个诉求：退换、免运费。这种复合场景，坐席一键 Escalate。看右边——AI Assist 区已经亮了，`gpt-realtime` 开始思考。"

**Step 5（AI 推理）**
> "这是 `gpt-realtime` 的推理链，它先判断需要哪些信息，然后**自主**调了三个工具：查订单、查关税、查保险。每一次调用、每一个参数，大家都看得到。最后，它生成了一段中文方案，直接念给客户听。"

**Step 6（坐席复述）**
> "坐席用英文确认一遍，客户中文回 '好的，就这样办'。整通电话结束。"

**Step 7（Audit）**
> "最后这一栏，是审计日志。原文、译文、推理步骤、工具调用、最终音频——**全部留底**，可回溯、可合规、可复盘。"

---

## 15.6 互动话术（Recap & Hook）

演示结束后立刻抛出（不要等观众提问）：

> "刚才大家看到的——中文原文识别，是 **whisper / gpt-4o-transcribe**；那一条双向同传，是 **gpt-4o-mini-translate**；AI 的三个工具调用 + 推理链，是 **gpt-realtime** 的 reasoning + function calling。三个模型，一条链路，全部跑在 Azure OpenAI 上。"

可选追问：

- "如果让你们把这个 demo 改造成自己业务的客服，第一个想换的工具会是什么？"（引导 Q&A）

---

## 15.7 风险预案（Failure Playbook）

| 场景 | 触发条件 | 应对 | 切换时间预算 |
|---|---|---|---|
| 网络抖动 | 云端 RTT > 1s 或 2 次 5xx | `Ctrl+L` 切到 `http://localhost:3000`，台词："我们切到本地副本继续，逻辑完全一致" | ≤ 5 秒 |
| 音频权限 | 浏览器没拿到麦克风 / 系统拒绝 | 操作员切到 BlackHole 虚拟输入，注入 `scripts/audio-samples/*.wav` | ≤ 10 秒 |
| Foundry 429 | 任一模型返回 `429 Too Many Requests` | 自动重试 1 次（已内置指数退避）；仍失败则前端自动切到备份 deployment（`rt-backup` / `tr-backup`） | 透明，无需口播 |
| 字幕乱码 | UTF-8 未生效，出现 `??` 或方块 | ① 在 AgentPane 右上角点"强制 UTF-8"；② 极端情况切英文单语模式（关闭 translate） | ≤ 5 秒 |
| 浏览器崩溃 | tab crash | 立刻打开预备的"录播 fallback"视频（`scripts/fallback/demo-recording.mp4`），台词："这是我们昨晚录制的同一段，先看效果再继续答疑" | ≤ 8 秒 |

**心法**：观众只在意"流畅"，不在意"原因"。任何切换都用**陈述句**带过，不解释、不道歉。

---

## 15.8 Q&A 预备题库

| 类别 | 常见问题 | 推荐答法（要点） |
|---|---|---|
| 成本 | "这一通电话大概多少钱？" | 按当前 pricing 估算：ASR ≈ $0.006/min、translate ≈ $0.002/句、realtime ≈ $0.06/min（输入）+ $0.24/min（输出）。8 分钟通话整体 < $0.50；批量场景可用缓存 / batch 进一步降。 |
| 生产化 | "从 demo 到生产差什么？" | 4 项：① 接入真实 SIP / WebRTC 网关；② 工具调用接公司 ERP / CRM；③ 审计日志接 SIEM；④ 加 PII 脱敏中间件。Azure Container Apps + Front Door 可直接上量。 |
| 模型选型 | "为什么不直接用 gpt-realtime 翻译？" | realtime 也能翻，但：① 专用 translate 模型延迟更低、单价更便宜；② 把"翻译"和"推理"解耦后，可独立替换 / A-B；③ 多 agent 架构更易做权责审计。 |
| 多语种 | "能不能换日语、阿拉伯语？" | 可以。translate 模型已覆盖 100+ 语种；只需改 system prompt 中的 `target_lang`，ASR 自动检测语种。RTL 语言需在前端开 `dir="rtl"`。 |
| 隐私合规 | "录音和文本会不会被模型训练？" | Azure OpenAI 默认不用客户数据训练；可在订阅级别签 zero-retention。审计日志写入客户自有 Storage，密钥客户托管（CMK）。 |
| 延迟 | "端到端多少 ms？" | 现场实测：ASR 首字 ~300ms、translate ~500ms、realtime tool-call 全链路 ~1.5–2.5s。区域同区是关键。 |
| 失败兜底 | "AI 答错了怎么办？" | 三层兜底：① 工具返回 schema 校验失败则不展示；② 坐席永远有最终决定权（Escalate 可撤销）；③ 审计日志全留底，可事后回放纠错。 |

---

## 15.9 录屏 / 直播配置建议

### OBS Studio

- **画布分辨率**：1920×1080
- **输出分辨率**：1920×1080
- **FPS**：30（直播）/ 60（录播精修）
- **编码器**：x264，CRF 18，preset `veryfast`（直播）/ `slow`（录播）
- **场景**：
  - `Scene 1 - Full Browser`：浏览器全屏 + 主讲摄像头右下角 320×180 PiP
  - `Scene 2 - AssistPane Zoom`：浏览器裁剪到右栏放大
  - `Scene 3 - Audit Log`：第三个 tab 全屏
- **快捷键**：`F1 / F2 / F3` 切换三个场景，操作员手动切

### 音频

- **采样率**：**48 kHz 单声道**（OBS、系统、浏览器三处全部统一，**采样率不一致是杂音首因**）
- **轨道分离**：
  - Track 1：系统输出（TTS 播放）
  - Track 2：主讲人麦克风
  - Track 3：副讲（坐席）麦克风
  - 后期可独立调音
- **降噪**：OBS 的 RNNoise 默认开；增益匹配到峰值 -6 dB，避免削波

### 网络（直播场景）

- 上行带宽 ≥ 10 Mbps，推流码率 6000 Kbps
- 备份 RTMP 推流地址提前测试

---

## 15.10 验收标准（Definition of Done）

本 demo 视为合格，当且仅当：

- [ ] **时长**：7 步在 8 分钟内完成（含开场，不含 Q&A）
- [ ] **流畅度**：观众侧无明显卡顿（> 2s 的空白），无字幕乱码，无 TTS 爆音
- [ ] **完整性**：3 个模型的能力点全部被口播明确点名（whisper / translate / realtime）
- [ ] **可追溯**：Audit JSONL 在 Step 7 时被打开并展示，包含 ≥ 1 条 reasoning + 3 条 tool_calls
- [ ] **零暴露 bug**：任何切换 / 兜底动作均未被观众明确察觉（事后问卷"是否注意到任何异常" < 10% 回答"是"）
- [ ] **复演**：同一脚本在不同操作员 / 不同会场连续两次跑通

如果任一项不达标，**回到 §15.1 重新走 checklist**，定位最弱环节后再上台。

---

## 附录 A：上台前 10 分钟"最后一遍"短清单

打印成卡片贴在显示器边框：

1. 电源插上了吗？
2. 通知关了吗？
3. 浏览器三个 tab 都在吗？
4. 音量 70%？
5. `fixtures.json` 时间戳是今天吗？
6. `/healthz` 返回 3/3 了吗？
7. 本地 docker 起着吗？
8. OBS 在录吗？
9. 秒表归零了吗？
10. 深呼吸。

---

← 返回 [README](../README.md)
