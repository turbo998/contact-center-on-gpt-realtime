# 07 · Cost Estimate

> ⚠️ 价格均基于 **2026-05 官方公告**（Microsoft Foundry Global Standard），实际计费以你 Azure 账单为准。三个模型计费方式不同，是设计成本控制时的关键点。

---

## 7.1 官方计费表

| 模型 | 部署 | 模态 | 输入 | Cached Input | 输出 |
|------|------|------|------|--------------|------|
| **gpt-realtime-translate** | Global Standard | Audio | $32.00 / 1M tokens | $0.40 / 1M | $64.00 / 1M |
|  |  | Text | $4.00 / 1M | $0.40 / 1M | $24.00 / 1M |
|  |  | Image | $5.00 / 1M | $0.50 / 1M | — |
| **gpt-realtime-whisper** | Global Standard | Audio | — | — | **$0.034 / 分钟** |
| **gpt-realtime-2** | Global Standard | Audio | — | — | **$0.017 / 分钟** |

**关键观察**：

- `whisper` 与 `realtime-2` 按 **音频分钟** 计费，单价低、容易估算
- `translate` 按 **token** 计费，audio token 单价高但通常 token 量小（不是按分钟扁平计）
- 三者计费颗粒不一致，**成本建模需要分开算**

---

## 7.2 单通通话成本测算（5 分钟跨境通话）

### 假设

- 客户和坐席各说话约 2.5 分钟（即 5 分钟通话内总人声约 5 分钟）
- 升级到 realtime-2 的时长约 1 分钟
- whisper 全程运行 5 分钟做合规留底
- translate 双向同传 5 分钟（按 token 估算）

### 估算

| 模型 | 用量 | 单价 | 小计 |
|------|------|------|------|
| `translate` audio in | ~150K tokens（5 分钟双向音频估算） | $32 / 1M | $4.80 |
| `translate` audio out | ~150K tokens | $64 / 1M | $9.60 |
| `whisper` | 5 分钟 | $0.034 / min | $0.17 |
| `realtime-2` | 1 分钟（高推理） | $0.017 / min | $0.017 |
| **合计** | | | **≈ $14.6** |

> ⚠️ translate 的 audio token 计量受**采样率、说话密度、双向音轨**等因素影响，**实测可能在 ±50% 范围内波动**。建议第一次跑完后用 Foundry 账单核对系数后再做月度估算。

### 较保守版本（开启缓存 + minimal reasoning）

| 模型 | 用量 | 单价 | 小计 |
|------|------|------|------|
| `translate` audio cached in | 50% cache hit | $0.40 / 1M | $0.03 |
| `translate` audio non-cached in | 75K tokens | $32 / 1M | $2.40 |
| `translate` audio out | 150K tokens | $64 / 1M | $9.60 |
| `whisper` | 5 分钟 | $0.034 | $0.17 |
| `realtime-2` (effort=minimal) | 1 分钟 | $0.017 | $0.017 |
| **合计** | | | **≈ $12.2** |

---

## 7.3 月度估算（1000 通 / 月）

| 场景 | 单通成本 | 月度 |
|------|----------|------|
| 标准估算 | $14.6 | **$14,600** |
| 保守估算（缓存 + minimal） | $12.2 | $12,200 |
| 极简版（只用 whisper + rt-2，无翻译） | ~$0.25 | $250 |

> 🚨 **跨境双向同传是成本大头**，因为 audio output token 单价 $64/1M，且每秒钟音频对应约 500-800 tokens。

---

## 7.4 成本优化建议

### A. translate
- **避免无人声片段送翻译**：前端做 VAD（Voice Activity Detection），静音时暂停推流
- **降低采样率到 16 kHz**（如果模型支持）—— 待官方确认
- **启用缓存**：reuse session 时利用 cached input 折扣

### B. whisper
- **按需启用**：只在通话被标记"合规存档"时打开；非合规通话用客户端 VAD 触发的本地 STT 也可
- **短通话先关再开**：通话前 10 秒可关，业务沟通开始后再开

### C. realtime-2
- **`reasoning.effort` 分档调度**：
  - 简单 FAQ → `minimal`（首响最快、成本最低）
  - 一般咨询 → `medium`
  - 复杂多步推理 → `high`（仅在 escalate 时）
- **避免长 context 滚雪球**：通话期间定期摘要压缩历史，避免 128K 上下文真的被吃满

### D. 通用
- **5 分钟硬性超时**（`MAX_CALL_DURATION_SEC=300`）—— 防止演示忘了挂断
- **演示账号配额上限**：在 Foundry 资源上设 daily quota，撞到自动停
- **预付费券**：Azure Sponsorship / MSFT for Startups 可申请额度

---

## 7.5 演示场景成本控制建议

针对**路演 Demo**（非生产）的具体建议：

| 控制点 | 建议值 |
|--------|--------|
| 单通时长上限 | 5 分钟（环境变量 `MAX_CALL_DURATION_SEC=300`） |
| `reasoning.effort` 默认 | `medium`，路演时切到 `high` 展示对比 |
| whisper 是否常驻 | 是（合规是演示亮点之一） |
| translate 静音抑制 | 是（前端 VAD） |
| 每日演示次数预算 | 20 通 × $15 ≈ **$300/天** |

---

## 7.6 计费监控

部署后建议立刻：

1. 在 Azure Portal → Cost Management → 设置预算告警（如月度 $500 → 邮件/Webhook）
2. 在 Foundry 资源上启用 Diagnostic Settings → 把 metrics 推送到 Log Analytics
3. 用 KQL 查询每通通话的 token / 分钟消耗：

```kusto
AzureDiagnostics
| where ResourceProvider == "MICROSOFT.COGNITIVESERVICES"
| where TimeGenerated > ago(1d)
| summarize total_tokens = sum(toint(OutputTokens_d)) by ModelDeploymentName_s, bin(TimeGenerated, 1h)
```

---

下一步：[08-risks-and-mitigations.md](./08-risks-and-mitigations.md) 看会有哪些坑。
