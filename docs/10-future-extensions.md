# 10 · Future Extensions

> 本期范围之外、但**值得在 v0.2+ 做**的扩展方向。按价值 × 工程复杂度排序。

---

## 10.1 接入真实 CRM / 工单系统

**价值**：⭐⭐⭐⭐⭐ ｜ **复杂度**：⭐⭐

替换 `app.tools.mock_crm` 为真实接口：

- Dynamics 365 Customer Service API
- Salesforce Service Cloud REST API
- Zendesk Support API
- 自建工单系统 OpenAPI

实施要点：

- 把 mock 的函数签名作为 contract，让接入方实现 adapter 模式
- 通过 OAuth 2 / API Key 集中管理凭据（Azure Key Vault + MI）
- 加 circuit breaker（如 `tenacity` + 超时降级），避免 CRM 拖垮通话

---

## 10.2 SIP 网关 / 真实电话号码

**价值**：⭐⭐⭐⭐⭐ ｜ **复杂度**：⭐⭐⭐⭐

让真实电话进来，而不是浏览器麦克风。Realtime API GA 时官方已支持 SIP 集成。

实施路径：

- **Azure Communication Services (ACS)** —— 申请号码、SIP trunk
- 用 ACS Call Automation + Media Streaming 抽出 PCM 流推给后端
- 后端把 PCM 喂给 Realtime API，把模型输出回传 ACS
- 客户拨打号码即可对话

延伸：

- 跨境号码（中国 + 英国本地号同时存在）
- IVR 前置（按 1 转中文坐席、按 2 转 AI）
- 录音留底（ACS 录音 + whisper 转写双保险）

---

## 10.3 Entra ID + RBAC

**价值**：⭐⭐⭐⭐ ｜ **复杂度**：⭐⭐

- 前端登录走 MSAL.js → Entra ID
- 后端 WS 鉴权：JWT 验证 + 自定义 claim → 区分坐席 / 主管 / 客户
- 通话录音/audit 权限按角色控制
- 与 [10.1] 配合 —— 调 CRM 时透传用户 token，实现"代客调用"

---

## 10.4 自动判断升级时机

**价值**：⭐⭐⭐⭐ ｜ **复杂度**：⭐⭐⭐

当前 Demo 是坐席手动点 Escalate。生产场景可加自动判断：

- **复杂度评分**：用 GPT-4o 实时分析最近 N 句对话，输出 0-1 复杂度
- **情绪识别**：检测客户愤怒/不满情绪，自动 escalate
- **关键词触发**：识别 "退款"、"投诉"、"客户经理" 等关键词
- **多模型协作**：translate / whisper 输出流式喂给一个 lightweight classifier

UI 改造：

- 显示 "AI 建议升级" 提示，坐席仍可一键确认 / 拒绝
- 升级理由透明可解释

---

## 10.5 Foundry Tracing + 全链路可观测性

**价值**：⭐⭐⭐⭐ ｜ **复杂度**：⭐⭐

- 启用 Foundry / Azure AI Foundry **Tracing**（基于 OpenTelemetry）
- 每通通话生成一个 trace，包含三模型调用 + 工具调用
- 集成 Application Insights → 看延迟分布、错误率、token 消耗
- KQL 查询样例提供在 README

---

## 10.6 多坐席 / 调度 / 转接

**价值**：⭐⭐⭐ ｜ **复杂度**：⭐⭐⭐⭐

- 一个客户 + N 个坐席 + 1 个主管的多端架构
- 坐席之间转接（"我帮您转到技术专家"）
- 主管 silent monitor（旁听不发声）
- 多技能组路由（中文母语 / 英文母语 / 售后 / 销售）

需要：会话状态 → Redis；WS broker → Pub/Sub；坐席空闲度模型

---

## 10.7 Knowledge Base 集成（RAG）

**价值**：⭐⭐⭐⭐ ｜ **复杂度**：⭐⭐⭐

rt-2 升级时除了 mock 工具，还能查询：

- 产品文档（Azure AI Search 向量索引）
- 历史工单库
- 售后政策

实施：

- 把 KB 检索包装成 rt-2 的工具 `search_knowledge_base(query)`
- 检索结果作为 context 注入 prompt

---

## 10.8 客户语音克隆 / 自定义音色

**价值**：⭐⭐ ｜ **复杂度**：⭐⭐⭐⭐⭐

- 用品牌定制音色播放译文 / AI 回复
- 注意合规：需要被克隆人书面授权、明显标识 AI
- 等 OpenAI 自定义音色 API 在 Foundry GA

---

## 10.9 离线 / 边缘部署

**价值**：⭐⭐ ｜ **复杂度**：⭐⭐⭐⭐⭐

某些行业（如政府、医疗）要求数据不出本地：

- whisper 本地化（用 openai-whisper / faster-whisper）
- translate 暂时无对应离线方案，业务退化为单语
- realtime-2 暂无离线方案
- 文档化"哪些功能可降级到本地"

---

## 10.10 多语种扩展

**价值**：⭐⭐⭐ ｜ **复杂度**：⭐⭐

translate 支持 70+ 输入、13 输出。可在 UI 加语言选择器：

- 客户：自动检测（whisper 自带 language detection）
- 坐席：从 13 种输出语种里选
- 单坐席可服务多语种客户

---

## 10.11 实时质检 / 坐席辅助 KPI

**价值**：⭐⭐⭐⭐ ｜ **复杂度**：⭐⭐⭐

通话期间实时：

- 通话节奏（坐席说话占比、平均响应时长）
- 情绪曲线
- 关键词覆盖率（是否问候、是否确认订单号）
- 合规检查（是否说了禁用语）
- 通话结束后自动生成评分报告

---

## 10.12 工程类增强

| 项 | 价值 |
|----|------|
| GitHub Actions CI/CD（lint + test + 自动部署） | 标准化 |
| Bicep What-If preview in PR | 部署安全 |
| Container Apps 蓝绿部署 | 零停机 |
| Renovate bot 维护依赖 | 长期可维护 |
| Pre-commit hooks（ruff、eslint、prettier） | 代码质量 |
| Storybook for frontend components | 组件复用 |
| Playwright E2E 自动化 | 回归保障 |

---

## 10.13 优先级建议

如果时间有限，建议按以下顺序推进 v0.2：

1. **10.5 Tracing** — 没有它后续优化都是盲调
2. **10.1 真实 CRM** — 业务价值最大、改动局部
3. **10.4 自动升级** — 体现"AI Native" 卖点
4. **10.7 RAG** — 让 rt-2 真正"懂业务"
5. **10.2 SIP 网关** — 解锁真实电话场景，质变

---

回到 [README](../README.md)。
