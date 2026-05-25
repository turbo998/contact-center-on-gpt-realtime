# 08 · Risks & Mitigations

## 8.1 风险矩阵

| ID | 风险 | 概率 | 影响 | 缓解措施 |
|----|------|------|------|----------|
| R1 | **模型 region/quota 受限**，目标区域可能没有模型可部署 | 中 | 高 | 部署前用 `az cognitiveservices account list-models` 确认；Bicep 把 `openaiLocation` 参数化；优先 Canada Central / France Central / India South |
| R2 | **realtime-2 仍在滚动上线**，演示当天可能未到达 | 中 | 高 | 部署时回退到 `gpt-realtime`（上一代）；UI 加 fallback 提示；在演讲口径里说明"滚动上线中" |
| R3 | **HTTPS 麦克风权限** —— 非 localhost 必须 HTTPS 才能拿到 mic | 高 | 中 | 本地走 `localhost`（豁免）；云上 Container Apps 默认 HTTPS；不要走纯 IP 演示 |
| R4 | **企业网络/防火墙拦 WebSocket** | 中 | 高 | 演示前现场连一遍；提供录屏 fallback（[02-business-scenario.md §2.6](./02-business-scenario.md)）；若必须演示走会议网络，提前用 4G 热点验证 |
| R5 | **三路并发音频带宽 / CPU** 占用过高 | 低 | 中 | 后端不做编解码只做转发；前端 24kHz 单声道 ≈ 48 kbps；Container App 至少 0.5 vCPU / 1 GiB |
| R6 | **演示成本累积** —— 现场反复跑导致计费快速攀升 | 中 | 中 | `MAX_CALL_DURATION_SEC=300` 硬超时；Foundry 设日预算告警；演示账号独立 |
| R7 | **跨语种 turn-taking 抖动** —— 双向同传可能出现两人同时说话导致音轨叠加 | 中 | 中 | 前端按 `is_speaking` 状态做 push-to-talk 提示；UI 加"对方正在说话"指示器；turn detection 用 Realtime API 内建的 server VAD |
| R8 | **音频回声/啸叫**（演示场景两台浏览器在同一房间） | 高 | 中 | 演示时坐席戴耳机；预录音频备份方案 |
| R9 | **工具调用幻觉** —— rt-2 可能调用不存在的工具或传错参数 | 低 | 中 | JSON Schema 严格定义；mock 函数对未知 `order_id` 返回明确 "not found"；prompt 限制只能用 3 个工具 |
| R10 | **whisper / translate 中文识别 / 翻译错误** —— 口音、术语 | 中 | 低 | 通过 `instructions` prompt 注入业务术语词表（订单号、产品名）；演示用清晰发音 |
| R11 | **首音延迟超标**（> 2s） | 中 | 高 | 后端与 Foundry 同区域；avoid base64 反复编码；前端 AudioWorklet 而非 ScriptProcessor；演示前测一次 |
| R12 | **认证失败 / Token 过期**（云上 MI） | 低 | 高 | `DefaultAzureCredential` 自带刷新；Bicep 一定要把 role assignment 加上；演示前跑健康检查 `/health` |
| R13 | **Realtime API 协议升级 breaking change** | 低 | 高 | `pyproject.toml` 锁定 `openai` 大版本；CI 在 schedule 上跑 smoke test 早发现 |
| R14 | **演示音频内容触发内容过滤** | 低 | 中 | 业务脚本预先审过；准备 2-3 套备用脚本 |
| R15 | **多浏览器 / 跨设备并发** —— 多人同时演示导致配额耗尽 | 中 | 中 | 在 Foundry 设配额；演示账号独立；UI 显示"当前并发数 / 上限" |

## 8.2 风险等级图（影响 × 概率）

```
         低概率        中概率        高概率
高影响  R5,R12,R13    R1,R2,R11,R6   R3
中影响  R9,R14        R7,R10,R15     R4,R8
低影响                R10             
```

**重点关注（高影响 × 高/中概率）**：R1、R2、R3、R4、R6、R11

## 8.3 演示当天 Checklist

- [ ] 提前 1 小时跑一次完整 6 步脚本，确认延迟 / 音质 / 工具调用
- [ ] 麦克风权限已授权，AudioContext 已通过用户交互"激活"
- [ ] 网络环境验证过（不走会议室拦截 WS 的网络）
- [ ] 录屏 fallback 已经准备好
- [ ] Foundry 当日额度还有余量
- [ ] 坐席戴耳机，避免回声
- [ ] 演讲口径熟练（[02-business-scenario.md §2.5](./02-business-scenario.md)）

---

下一步：[09-acceptance-criteria.md](./09-acceptance-criteria.md) 看怎样算"做完了"。
