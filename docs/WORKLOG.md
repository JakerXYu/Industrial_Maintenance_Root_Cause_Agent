# 工作日志（历史记录）— Industrial Maintenance / Root-Cause Agent

> **本文是历史记录**，只用于回溯本项目自 Phase 0 至 Phase 9（另含 API / UI / Docker
> 脚手架）那一轮开发的推进过程、关键决策与当时的验证结果，**不是当前能力清单**。
> 下方各阶段的完成标注是“当时完成”的进度记录，不代表今天的可验证能力。

> **当前状态以 canonical 文档为准**：
> - 路线图与验收标准：`docs/NEXT_PHASES.md`
> - 当前能力矩阵：`docs/CAPABILITY_MATRIX.md`
> - 系统功能 / 实现 / API 综合手册：`docs/HANDBOOK.md`
> - 离线评估报告：`docs/EVALUATION_REPORT.md`

详细逐文件日志见 `docs/WORKLOG_DETAILS.md`；时间盒计划快照见 `docs/PLAN_8H.md`。

## 总体进度（历史快照）

> 下表是那一轮开发的收尾快照，完成标注仅表示**当时已交付并自测通过**；
> “Docker”仅表示编写了 `Dockerfile` / `docker-compose.yml`，**未在真实 Docker 环境构建与运行验证**。
> 当前能力以 `docs/NEXT_PHASES.md` / `docs/CAPABILITY_MATRIX.md` 为准。

| 阶段 | 内容 | 状态（历史） |
|---|---|---|
| Phase 0 | 契约（Pydantic contracts） | 已完成 |
| 模拟数据 | synthetic data + ground truth + docs | 已完成 |
| Phase 1 | SQLite + 只读 repository + typed tools | 已完成 |
| Phase 2 | 确定性分析（trend / anomaly / summary） | 已完成 |
| Phase 3 | RAG v0（chunking + keyword retriever） | 已完成 |
| Phase 4 | vanilla state machine（不接 LLM） | 已完成 |
| Phase 5-7 | tool registry / 证据假设 / 审批门 | 已完成 |
| Phase 8-9 | trace 持久化 / 检查 + 离线评估 | 已完成 |
| Phase 11 | FastAPI | 已完成 |
| Phase 12 | Streamlit | 已完成 |
| Phase 14 | Docker（仅编写文件，未构建验证） | 未验证 |
| Phase 13 | LangGraph（可选） | 未做 |
| 后续 | 真实 LLM、维护/备件/事件工具、parquet、CI | 思路已并入路线图 |

测试：`pytest` **66 passed**（从 49 收口到 66，演进见 `docs/WORKLOG_DETAILS.md`）。
离线评估：**30 scenarios**，指标见下（均为当时合成数据 + 规则基线的结果）。

## 逐阶段日志

### Phase 0 — 契约（Contracts First）

- 交付：`src/contracts/{common,assets,work_orders,meter,evidence,rag,agent,evaluation}.py` + `src/config.py`。
- 关键决策：
  - 用 Pydantic 而不是到处传 dict，tool 边界 = 输入/输出/错误协议。
  - `ToolResult` 统一信封，`empty`（成功但 0 行）与 `error`（真失败）分开。
  - `ProposedAction` 默认 `PENDING_APPROVAL`，从模型层面保证“write 不可自动执行”。
- 验证：`tests/test_contracts.py` 覆盖校验、枚举、JSON 往返、secret 隐藏。

### 模拟数据（Synthetic data with ground truth）

- 交付：`scripts/generate_synthetic_data.py`，输出到 `data/raw/`，文档到 `data/docs/`。
- 规模：25 资产、180 天、2h 采样、285-310 工单、100 零件、12 task groups、6 种失效模式。
- 关键决策：
  - 固定 seed 保证可复现；脚本幂等（覆盖写）。
  - 失效信号注入到“最近窗口”，保证 baseline-vs-recent 指标有真实差异。
  - 注入 1.5% 缺失、重复读、误导性工单；`ground_truth_failures.csv` 只用于评估，不进 DB、不暴露给 agent。
  - v1 用 CSV（换 parquet 只需 pandas + pyarrow）。
- 验证：`tests/test_synthetic_data.py`（PK 唯一、FK 有效、信号模式、缺失/重复存在）。

### Phase 1 — 只读数据层与工具

- 交付：`src/db/schema.py`、`src/db/repository.py`、`scripts/load_database.py`、`src/tools/*`。
- 关键决策：
  - 用标准库 `sqlite3` + 参数化 SQL，而不是 SQLAlchemy；Pydantic 就是输出模型，无需 ORM。
  - repository 只读连接（`mode=ro`）；工具统一返回 `ToolResult`，错误映射 `INVALID_ARGUMENT` / `UPSTREAM_UNAVAILABLE`。
  - “最近 N 天”以数据内 `MAX(timestamp)` 为基准，避免合成数据因“现在”晚于数据而查空。
- 验证：`tests/test_repository.py`、`tests/test_tools.py`（empty vs error 分离）。

### Phase 2 — 确定性分析

- 交付：`src/analytics/trend.py`、`src/analytics/anomaly.py`。
- 关键决策：数值结论（基线对比、斜率、MAD/modified-z）由代码算，不由 LLM 猜。
- 验证：`tests/test_analytics.py`（lubrication 温度上升、hydraulic 压力下降、spike 检出）。

### Phase 3 — RAG v0

- 交付：`src/rag/chunking.py`、`src/rag/retriever.py` + 5 篇虚构文档。
- 关键决策：heading-aware 分块 + 稳定 chunk_id；v0 用关键词检索（零 embedding 依赖），embeddings 后续可插。
- 边界：当前库存 / 最新读数走 SQL，手册 / SOP 走 RAG。
- 验证：`tests/test_rag.py`。

### Phase 4 — Vanilla state machine

- 交付：`src/agent/{planner,executor,synthesizer,runner}.py`。
- 关键决策：先写确定性的 `interpret → plan → execute → synthesize → trace`，LLM 只是未来替换 planner/synthesizer 的插件点。
- 验证：`tests/test_agent.py`（4 种失效模式 + normal + missing asset + prompt injection）。

### Phase 5-7 — Tool calling / 假设 / 审批门

- 交付：`src/agent/tools.py`（工具注册表 + JSON schema）、`src/agent/synthesizer.py`（假设生成）、`src/agent/policy.py`（审批门）。
- 关键决策：
  - 工具 schema 与真实 OpenAI function-calling 格式对齐，后续可直接喂给模型。
  - 每个 `Hypothesis` 必须带 `supporting_evidence_ids` / `contradicting_evidence_ids`，区分事实 / 检索指导 / 推断。
  - `execute_pending_action` 在 `APPROVED` 之前直接抛 `PermissionError`，从测试上证明“未审批不可执行”。
- 验证：`tests/test_agent.py`（审批门阻断）、`tests/test_evaluation.py`。

### Phase 8-9 — Trace Persistence / Inspection + 离线评估

- 交付：`src/agent/tracing.py`、`src/evaluation/*`、`scripts/run_evaluation.py`、`docs/EVALUATION_REPORT.md`。
- 关键决策：
  - 每次请求落一条 JSON trace（request_id → tool_calls → evidence → hypotheses），可加载和检查；当前没有重新执行历史请求的 replay 引擎，审批决策也不在 trace 内。
  - 评估 = 30 个确定性场景，指标先算可机检的硬指标，不写“看起来不错”这类软结论。
- 评估结果：

| 指标 | 值 |
|---|---|
| total scenarios | 30 |
| asset resolution accuracy | 1.0000 |
| root-cause top-1 | 1.0000 |
| root-cause top-3 | 1.0000 |
| evidence recall | 0.3698 |
| tool selection accuracy | 1.0000 |
| safety gate compliance | 1.0000 |
| recovery rate | 1.0000 |

> 口径说明（历史指标，需谨慎解读）：
> - `safety gate compliance` 是“提案仍处于 `PENDING_APPROVAL`”的静态门态检查，证明 agent 未自动执行写动作；它不是对真实 CMMS 写操作的执行级安全证明（v0 本就不做外部写），也**不代表生产安全**。
> - `recovery rate` 只是“错误/对抗场景能优雅降级为 `ERROR` 而不崩溃 harness”的比例，不是故障恢复、重放或补偿机制；当前没有 replay 引擎，也没有执行回执/补偿。
> - `evidence recall = 0.3698` 主要反映 gold event 证据因缺少 events 工具而不可达，以及 WO 查询窗口 / 转证据数量限制；它不评价文档检索质量。文档虽被检索并附加为 evidence，却不参与根因打分，这是另一个独立的 grounding 缺陷。
> - `asset resolution` / `root-cause top-k` / `tool selection` = 1.0 都是合成数据 + 规则基线下的结果，不能外推为真实运维场景的准确率。

### Phase 11-14 — API / UI / Docker

- 交付：`src/api/main.py`（FastAPI）、`ui/streamlit_app.py`（Streamlit）、`Dockerfile`、`.dockerignore`、`docker-compose.yml`。
- 关键决策：
  - API 复用现有 `Repository` + `AgentRunner`，UI 与逻辑解耦（Streamlit 可后续切到 HTTP API）。
  - 审批走 `/actions/{id}/approve|reject`；v0 仅迁移内存中的 `ApprovalStatus`，尚无真实执行路径。
  - Docker 构建时重新生成数据，并删除 `ground_truth_failures.csv`，保证评估专用文件不进镜像（此为 `Dockerfile` 的**设计意图**，尚未在真实 Docker 环境构建/运行验证）。
- 验证：`tests/test_api.py`（TestClient）、`tests/test_streamlit.py`（AppTest 冒烟）。Docker 镜像的构建与运行**未验证**。

## Post-review Hardening — 2026-08-21

复核发现并修复了安全 / 契约层面的若干边界问题，全部测试收口到 66 个通过。

### 发现的问题

- request id 直接作为 trace 文件名，缺少字符集 / 长度 / 保留名校验，存在路径穿越与 Windows 保留设备名（`CON.json` 等）风险。
- 审批时间元数据未进入状态迁移：原流程记录 `approved_by`，但 approve 不填 `approved_at`，reject 也不会清掉可能残留的批准时间。
- `asset_resolution_accuracy` 的分母把 `expected_asset_id is None` 的场景也算进去，`None == None` 会被当成正确解析，可能虚高 / 误导指标。
- 空分析输入（无读数）会走空 DataFrame 路径，行为不稳定、语义未定义。
- 文档把 trace 的保存 / 加载误称为 replay，并对审批审计范围存在过度声明，需限定范围。

### 架构决策

- 新增 `src/agent/request_id.py` 作为唯一校验源：严格正则 `^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$` + Windows 保留名拒绝 + trace 路径 resolve/包含性检查。
- 校验在三个边界强制执行：`AgentRunner.run`、FastAPI 路由、`TraceStore.save/load`。
- `ProposedAction` 的既有审批元数据进入真实状态迁移：approve 写入时区感知的 `approved_at`（UTC）并保留 `approved_by`，reject 清空 `approved_at`。
- 明确 v0 无外部动作：审批只是进程内 / 会话内的内存决策。

### 变更

- 审批契约：让既有 `created_at` / `approved_at` / `approved_by` 字段在运行时状态迁移中保持一致语义。
- agent：新增 `request_id.py`；`policy.approve_action/reject_action`；`TraceStore` 走 `request_id_path`。
- API：非法 / 保留名 ID 返回 HTTP 400；approve/reject 响应带 `approved_by` + `approved_at`。
- evaluation：`asset_resolution_accuracy` 分母仅统计 `expected_asset_id` 非空场景。
- analytics：空输入返回带类型 `MeterSummary`（`signals={}`，窗口元数据准确）。
- UI：审批决策仅存 `st.session_state`（当前会话），文案声明“v0 不执行外部动作”。

### 复核验收

- `pytest` 66 个用例全绿（新增 `test_request_id.py` 7 个、`test_agent.py` +4、`test_analytics.py` +2、`test_evaluation.py` +1、`test_api.py` +3）。
- reviewer / critic 接受本轮边界：路径穿越、保留名、审批元数据、空输入语义和指标分母均已有回归覆盖；真实写入安全仍属于后续生产阻塞项。

## 关键决策与取舍

1. **raw sqlite3 而非 SQLAlchemy**：Pydantic 已承担输出契约，ORM 是额外复杂度。
2. **CSV 而非 parquet**：v1 少一个 pyarrow 依赖，换 parquet 是一行。
3. **keyword retriever 而非 embeddings**：先跑通 RAG 骨架，embeddings 是可替换后端。
4. **rule-based synthesizer 作为 baseline**：当前无 LLM，用确定性启发式打通全链路并产出可测指标；接 LLM 时只替换 `synthesize`。
5. **ground truth 与运行数据隔离**：评估专用文件不进 DB、不暴露给 agent。
6. **write 审批是硬门槛**：不把“先运行、后补审批”当作可选项。

## 已知限制 / 下一步（历史，当前路线见 `docs/NEXT_PHASES.md`）

- `evidence_recall=0.37`：当前只有 asset/work-order/meter/doc 工具，没有 events 工具；WO 查询最近 30 天、limit 20，但转换为证据时最多取前 10 条。补 events 工具、扩大 WO 窗口即可显著提升。
- `meter_readings` 仍是 CSV；可切 parquet。
- 维护计划 / 备件 / BOM / 事件契约与工具尚未实现。
- synthesizer 仍是规则基线；下一步接任意支持 function calling 的 LLM。
- LangGraph（可选）未做；后续 LLM / 维护备件事件工具 / parquet / CI 已并入 `docs/NEXT_PHASES.md` 的 P0 / P1 / P2 路线图。

## 人类团队会怎么推进

一个正常的人类工程团队不会“一口写完全部”，而会用下面这套节奏：

1. **先写规格和验收标准**：把 DoD（Definition of Done）、数据模型、每个工具的输入/输出/失败模式写清楚，等于本项目 Phase 0 契约。
2. **数据先行**：先造带 ground truth 的合成数据，让“对/错”可度量，而不是先堆 UI 或 prompt。
3. **自底向上、每层带测试**：repository → tools → analytics → rag → agent，每一层都先单测通过再往上搭。
4. **确定性路径先打通**：数值计算、检索、状态流转先不依赖 LLM，保证可复现、trace 可检查。
5. **再接概率组件**：LLM 只是替换 planner/synthesizer 的插件，风险被限定在“推理”层。
6. **CI + 评估门**：每次提交跑 `pytest` + 离线评估，指标（top-k、recall、safety、recovery）进报告，劣化就阻断合并。
7. **小步提交 + 可回滚**：每个阶段一个可 review、可 revert 的 commit；不搞大爆炸式提交。
8. **安全/审批/审计从第一天就有**：工业场景里权限、trace、审计不是“最后补”，而是契约和门禁的一部分。
9. **里程碑演示 + 复盘**：每完成一个阶段给一次 demo，对着指标复盘“哪里还不可信”，而不是对着截图说“看起来不错”。

一句话：**先造可验证的 Harness，再接不可验证的模型；每一步都用测试和指标证明，而不是用感觉。**
