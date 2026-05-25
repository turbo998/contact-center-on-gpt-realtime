# 01 · Overview

## 1.1 三个模型，三种角色

2026 年 5 月，OpenAI 与 Microsoft 联合宣布在 **Microsoft Foundry** 上线三款新音频模型，全部通过 **Realtime API** 访问：

| 模型 | 角色定位 | 核心能力 |
|------|----------|----------|
| **`gpt-realtime-translate`** | 实时同传引擎 | 连续音频流双向翻译，不切片、不缓冲；70+ 输入语种 / 13 输出语种 |
| **`gpt-realtime-whisper`** | 流式速记员 | 低延迟语音转文本，可与翻译/对话并行运行 |
| **`gpt-realtime-2`** | 会推理的语音助手 | 在语音层内嵌推理（`reasoning.effort` 四档），128K 上下文，支持工具调用 |

> 三者在 Foundry 上**独立计费、独立部署**，但被设计成可以**协同工作**：translate 负责跨语言、whisper 负责原文留底、realtime-2 负责复杂决策。

## 1.2 为什么要"串"起来

单独使用任何一个模型都能解决一个局部问题，但真实业务往往同时需要：

- **跨语言沟通** → 单用 translate 即可
- **合规留底原文** → 必须用 whisper（translate 输出的是译文，而不是原文）
- **复杂业务决策** → 必须用 realtime-2（前两个模型不具备推理能力）

把三个模型组合起来，才能完整覆盖一个**真实跨境客服通话**的全部需求 —— 这正是 OpenAI 在公告中明确指出的旗舰用例。

```
单 translate            ❌ 没有原文存档，过不了合规
单 whisper              ❌ 客户和坐席听不懂对方语言
单 realtime-2           ❌ 不支持持续翻译，跨语种体验割裂

translate + whisper + realtime-2  ✅ 业务闭环
```

## 1.3 本 Demo 想证明什么

1. **三模型可以在同一通通话里同时工作**，不互相干扰
2. 通过 `reasoning.effort` 可调节，**延迟与推理深度可以权衡**
3. **架构清晰**：用三条独立 WebSocket 通道做隔离，便于排查和扩展
4. **工程成本可控**：一份 FastAPI 后端 + 一份 Next.js 前端，**本地 docker-compose 起，云上 `azd up` 起**
5. **业务可解释**：UI 上能同时看到 *原文 / 译文 / 推理 trace / 工具调用*，方便向非技术干系人讲故事

## 1.4 适用人群

- **方案架构师 / 售前** —— 需要一个能演示的客户呼叫中心样板
- **AI 应用开发者** —— 需要一份能落地的 Realtime API 三模型集成范例
- **客服 / 业务方** —— 需要直观理解这套技术能为业务带来什么

## 1.5 不在范围内

本仓库**不**覆盖以下内容（参见 [10-future-extensions.md](./10-future-extensions.md)）：

- 接入真实 CRM 或工单系统
- SIP 网关 / 真实电话号码接入
- 企业级身份认证（Entra ID + RBAC）
- 多坐席调度、转接、技能组路由
- 情绪分析、自动质检、坐席辅助 KPI

## 1.6 参考资料

- 官方公告：*A New Chapter for Realtime AI: Reasoning, Translation, and Real-Time Transcription* — Azure AI Foundry Blog (2026-05)
- 模型目录：<https://ai.azure.com/catalog/models/gpt-realtime-translate>
- Microsoft Docs：`articles/foundry/openai/includes/gpt-realtime-translate.md`
- OpenAI API Docs：<https://developers.openai.com/api/docs/models/gpt-realtime-translate>
