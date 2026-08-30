# 8 小时推进计划（Harness-First）— 已归档时间盒计划

> **本文是已归档的时间盒计划**：记录那一轮“8 小时”内按 Harness-First 顺序推进的原计划与当时快照，
> 仅作历史档案保留，**不再更新，也不是当前状态或能力清单**。
> 当前状态与下一步以 `docs/NEXT_PHASES.md`（路线图）与 `docs/CAPABILITY_MATRIX.md`（能力矩阵）为准；
> 系统手册见 `docs/HANDBOOK.md`，开发日志见 `docs/WORKLOG.md` / `docs/WORKLOG_DETAILS.md`。

> 参考仓库 `learn-claude-code` 的核心判断：Agency 来自模型，工程要造的是 Harness。
> 对本项目而言，Harness = 只读 typed tools + 确定性分析 + RAG 知识 + 审批权限 + trace/评估。
> 所以顺序永远是：契约 → 模拟数据 → 只读工具 → 确定性分析 → RAG → Agent Loop → 审批 → 评估。

## 状态快照（8 小时会话结束时的原始历史快照，保持不变）

- [x] Phase 0：契约（`src/contracts/*` + `src/config.py`）
- [x] 模拟数据：`scripts/generate_synthetic_data.py` + ground truth + 5 篇 docs
- [x] 只读数据层：`src/db/schema.py` + `repository.py` + `scripts/load_database.py`
- [x] 只读工具：`src/tools/{asset,work_order,meter}_tools.py`
- [x] 确定性分析：`src/analytics/{trend,anomaly}.py` -> `MeterSummary`
- [x] RAG v0：`src/rag/{chunking,retriever}.py`（heading-aware + keyword retriever）
- [x] Phase 4：vanilla state machine（先不接 LLM，跑通状态流转）
- [x] Phase 5-7：tool registry / 证据假设 / 审批门
- [x] Phase 8-9：trace 持久化 / 检查 + 离线评估（30 scenarios）
- [x] Phase 11：FastAPI（`src/api/main.py`）
- [x] Phase 12：Streamlit（`ui/streamlit_app.py`）
- [x] Phase 14：Docker（`Dockerfile` + `docker-compose.yml`，仅编写文件，未构建验证）
- [ ] Phase 13：LangGraph（可选，思路见 `docs/NEXT_PHASES.md`）

测试：`pytest` 全绿（49 passed）。
评估：30 scenarios；root-cause top-1/top-3 = 1.0，proposal gate-state compliance = 1.0，recovery = 1.0，evidence recall = 0.37。
> 口径提醒：`recovery = 1.0` 仅表示错误/对抗场景优雅降级为 `ERROR`，非故障恢复/重放能力；`proposal gate-state compliance` 非生产安全证明；上述均为合成数据 + 规则基线结果。
详细记录见 `docs/WORKLOG.md` 与 `docs/EVALUATION_REPORT.md`。
后续思路已重写为 `docs/NEXT_PHASES.md` 的 P0 / P1 / P2 路线图。

## Post-plan 状态（2026-08-21 更新，同样为历史记录）

> 上方的“状态快照”是 8 小时会话结束时的历史记录（49 passed）。本节为后续安全 / 契约加固后的
> 历史快照（66 passed），**并非当前状态**。当前状态以 `docs/NEXT_PHASES.md` / `docs/CAPABILITY_MATRIX.md` 为准。

- 测试：`pytest` **66 passed**（原 49 + 新增 request_id 7 / agent 4 / analytics 2 / evaluation 1 / api 3）。
- 安全加固：request id 严格校验（`^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$` + Windows 保留名拒绝 + trace 目录边界检查），在 API / `AgentRunner` / `TraceStore` 三处强制。
- 审批：approve 记录 `approved_by` 与时区感知 `approved_at`；reject 清空 `approved_at`；审批为进程内 / 会话内内存决策，v0 不执行外部动作。
- 指标口径：`asset_resolution_accuracy` 分母排除 `expected_asset_id is None` 场景；空分析输入返回带类型 `MeterSummary`（`signals={}`）。
- prompt-injection 场景与 30+ 离线评估场景均已完成（见“剩余队列”的完成标注）。

## 8 小时时间盒

| 时段 | 阶段 | 交付物 | 验收标准 |
|---|---|---|---|
| 0:00-1:30 | 模拟数据 | 25 assets / 180d / 2h 采样 / 6 种失效模式 / ground truth / 数据瑕疵 | 脚本可复现、幂等；PK 唯一、FK 有效、注入失效信号可测 |
| 1:30-3:00 | 只读数据层 | `data/industrial.db` + `src/db/schema.py` + `repository.py` + `scripts/load_database.py` | 参数化 SQL；empty vs error 分离；typed 输出 |
| 3:00-4:30 | 只读工具 | `src/tools/{asset,work_order,meter}_tools.py` | 每个工具返回 `ToolResult`；错误与空结果可区分 |
| 4:30-6:00 | 确定性分析 | `src/analytics/trend.py` + `anomaly.py` → `MeterSummary` | baseline vs recent、slope、MAD 异常；LLM 不读原始行 |
| 6:00-7:00 | RAG | `src/rag/chunking.py` + 本地检索 + 5 篇虚构文档 | heading-aware chunk、稳定 chunk_id、引文元数据 |
| 7:00-8:00 | Agent Loop 骨架 | `src/agent/state.py` + 最小状态机 + 审批门 stub + trace 占位 | 状态流转可测；write 在 APPROVE 前不可执行 |

## 为什么是这个顺序

1. **数据先行**：没有带 ground truth 的合成数据，后面所有“证据/评估”都是空谈。
2. **工具先行于 LLM**：工具是 Harness 的“手”，必须可独立测试。
3. **确定性分析外置**：数值结论（趋势/异常/基线对比）由代码算，不由 LLM 猜。
4. **RAG 只放非结构化知识**：当前库存/最新读数走 SQL，手册/SOP 走 RAG。
5. **审批与 trace 是工业硬门槛**：read 路径 trace 可加载和检查，但当前没有 replay 引擎；write-like proposal 必须先审批，真实执行与审批审计仍是后续生产阻塞项。

## 剩余队列（历史遗留，已并入 `docs/NEXT_PHASES.md` 路线图）

- 维护计划 / 备件 / BOM / 事件等契约与工具（当前先聚焦 asset / work order / meter）。
- `meter_readings.parquet`：v1 先写 CSV，换成 parquet 只需 pandas + pyarrow 一行。
- 真正的 LLM tool-calling（Phase 5）：用任意支持 function calling 的模型，不锁厂商。
- ~~故障注入与 prompt-injection 测试（Phase 10）~~ → 已完成：prompt-injection 场景与测试已落地（见 Post-plan 状态）。
- ~~30+ 离线评估场景与指标（Phase 9）~~ → 已完成：30 场景 + 7 项质量指标（另含场景总数）已落地（见 Post-plan 状态）。
