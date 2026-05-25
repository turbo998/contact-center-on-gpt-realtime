# 09 · Acceptance Criteria

## 9.1 总体验收标准

Demo 实现完成后，需满足以下**全部**条件才视为达成验收：

### 功能性

- [ ] **AC-1**：客户用中文说话，坐席听到英文译音 + 看到中文原文字幕，**两者来自不同模型**（translate vs whisper）
- [ ] **AC-2**：坐席用英文说话，客户听到中文译音
- [ ] **AC-3**：UI 三栏（Customer / Agent / AI Assist）同时显示对应内容
- [ ] **AC-4**：点击 Escalate 按钮后，AI Assist 面板激活，5 秒内有第一条推理 trace 出现
- [ ] **AC-5**：realtime-2 至少调用一次 mock 工具（`get_order` / `check_tariff` / `check_insurance`），UI 上可见参数与返回
- [ ] **AC-6**：通话结束后生成 `audit-{call_id}.jsonl`，包含原文（whisper）、译文（translate）、推理 trace + 工具调用（rt-2）三类事件
- [ ] **AC-7**：能完整跑通 [02-business-scenario.md §2.3](./02-business-scenario.md) 的 6 步脚本

### 非功能性

- [ ] **AC-8**：首音延迟（从客户开始说话到坐席听到第一个译文音节）**≤ 1.5s**
- [ ] **AC-9**：whisper 首字幕延迟 **≤ 0.8s**
- [ ] **AC-10**：realtime-2 在 `reasoning.effort=high` 下首响延迟 **≤ 3s**
- [ ] **AC-11**：UI 在 5 分钟通话内**不掉帧、不卡顿**
- [ ] **AC-12**：浏览器 Console **无 error**、WS 不出现意外断开
- [ ] **AC-13**：5 分钟通话总成本 **≤ $20**（基于 `effort=medium`）

### 工程

- [ ] **AC-14**：`docker compose up` 一次成功，无需手动调试
- [ ] **AC-15**：`azd up` 一次成功，云端 URL 能复现 AC-1 ~ AC-7
- [ ] **AC-16**：`azd down --purge` 能干净清理所有资源
- [ ] **AC-17**：后端 `pytest` 全绿，覆盖率 ≥ 70%
- [ ] **AC-18**：README 一屏内可看懂项目意图，docs/ 全部链接互通
- [ ] **AC-19**：repo 含 LICENSE (MIT)、`.gitignore`、`.env.example`
- [ ] **AC-20**：代码通过 `ruff check` + `npm run lint` + `npm run typecheck`

## 9.2 Demo 黄金路径（路演前必跑一遍）

```
1. 打开两个浏览器窗口（或两台设备）
   - 窗口 A：http://<deploy-url>/?role=customer
   - 窗口 B：http://<deploy-url>/?role=agent

2. 两边都点击「Start Call」，授权麦克风

3. 窗口 A 说中文：
   "你好，我上周买的咖啡机收到时漏水，订单号 A12345。"
   → 窗口 B 应在 ≤ 1.5s 内听到英文译音
   → 两个窗口都应看到对应字幕

4. 窗口 B 说英文：
   "Sorry to hear that. Let me check the order."
   → 窗口 A 应听到中文译音

5. 窗口 A 说中文：
   "我希望退货换新，但关税和保险我不想自己出。"
   → 窗口 B 点击「Escalate to AI」

6. 等待 3 秒，AI Assist 面板应出现：
   - 推理 trace 多条
   - 工具调用 3 个：get_order → check_tariff → check_insurance
   - 最终方案音频播出

7. 任一窗口点击「End Call」
   → 显示「通话记录已存档」
   → 下载或查看 audit-{id}.jsonl，确认三类事件齐全

8. 检查 Foundry 账单（next day）确认成本未失控
```

## 9.3 Demo 失败案例（明确不合格）

- ❌ 译音断断续续 / 时长超过 3s 才出现
- ❌ 字幕只显示一次性结果，没有 incremental（流式）效果
- ❌ Escalate 后 trace 面板空白超过 5s
- ❌ rt-2 没有触发任何工具调用就直接给答案（说明 prompt 没设置好）
- ❌ audit JSONL 缺失任一事件类型
- ❌ 演示过程中需要刷新页面 / 重启容器才能恢复
- ❌ 单通通话成本 > $30

## 9.4 路演通过标准

针对**对外路演**，建议附加：

- [ ] 演讲人能用 30 秒讲清楚业务价值（参见 [02-business-scenario.md §2.5](./02-business-scenario.md)）
- [ ] 现场演示流畅，无技术故障打断
- [ ] 听众能用一句话复述出三个模型各自的角色
- [ ] 至少有 1 个听众提出可落地的应用场景延伸

---

下一步：[10-future-extensions.md](./10-future-extensions.md) 看本期之后可以做什么。
