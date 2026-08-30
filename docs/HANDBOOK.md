# Industrial Maintenance / Root-Cause Agent — 系统手册（当前实现参考）

> 本文是**当前实现（确定性 baseline，未接 LLM）的权威参考**。面向阅读者说明系统目标、
> 功能设计、具体实现、数据模型、API 接口、运行方式、安全模型与扩展点。
> 能力矩阵、评估方法学、安全模型与面试讲解分别见 `CAPABILITY_MATRIX.md`、
> `EVALUATION_METHODOLOGY.md`、`SAFETY_AND_THREAT_MODEL.md`、`INTERVIEW_GUIDE.md`。

## 1. 系统概览

这是一个「小规模但架构完整」的工业维护 / 根因分析 Agent。它通过结构化工具查询设备、
工单、计量趋势和维修文档，基于证据形成根因假设；所有写类动作都必须经过人工审批。

核心目标不是「做一个维修聊天机器人」，而是演示一个 **可验证、可观测、可审批** 的
工业 Agent Harness：LLM 是未来后置的概率推理组件，外围是确定性软件系统。

### 核心原则

- **LLM 不是 system of record**：真实状态由工具查，数值结论由代码算；LLM（未来）只做推理与表达。
- **empty ≠ error**：空结果（`empty=True`）与工具失败（`ok=False`）是两回事。
- **read 自由，write 审批**：只读工具自动执行；任何写类动作先产出 `ProposedAction`，显式 `APPROVED` 后才可执行。
- **typed everywhere**：模块边界用 Pydantic 契约，不传裸 dict。
- **证据带 source-id，但 grounding 弱**：每条假设带 `supporting_evidence_ids` / `contradicting_evidence_ids`（事实、检索指导、推断分开），但当前检索文档不参与根因打分（见第 11.1 节 RAG 限制）。

## 2. 现状架构 vs 目标架构

> 本文档自始至终区分「已实现的 current」与「规划的 target」。当前代码里**没有** CLI、
> **没有** LLM、**没有** LangGraph；只有 API、Streamlit UI 与确定性状态机。

### 2.1 Current（已实现，确定性 baseline）

```text
┌──────────────────────────────────────────────┐
│ Streamlit UI / FastAPI                        │
│ question + approve/reject + trace inspect     │
└──────────────────────┬───────────────────────┘
                       ▼
┌──────────────────────────────────────────────┐
│ AgentRunner（src/agent）                      │
│ interpret → plan → execute → synthesize       │
│ → policy(approval) → trace                    │
└────────┬──────────────────────────┬──────────┘
         │                          │
         ▼                          ▼
┌──────────────────┐      ┌───────────────────┐
│ Typed Read Tools  │      │ RAG Retriever      │
│ asset / WO / meter│      │ chunking + keyword │
└────────┬──────────┘      └────────┬──────────┘
         ▼                          ▼
┌──────────────────┐      ┌───────────────────┐
│ SQLite (mode=ro) │      │ data/docs/*.md     │
└────────┬──────────┘      └───────────────────┘
         ▼
┌──────────────────────────────────────────────┐
│ Deterministic Analytics（trend / anomaly）    │
└──────────────────────────────────────────────┘
```

### 2.2 Target（未实现，设计见 `NEXT_PHASES.md`）

```text
┌──────────────────────────────────────────────┐
│ Streamlit UI / FastAPI                        │
└──────────────────────┬───────────────────────┘
                       ▼
┌──────────────────────────────────────────────┐
│ AgentRunner                                   │
│ LLM interpret/plan（仅选已注册 read 工具）     │
│ → execute（同一套 tools / analytics / RAG）   │
│ → LLM synthesize（structured output）         │
│ → policy(approval) → trace                    │
└────────┬──────────────────────────┬──────────┘
         │                          │
         ▼                          ▼
┌──────────────────┐      ┌───────────────────┐
│ Typed Read Tools  │      │ RAG Retriever      │
│ （不变）           │      │ （不变）           │
└────────┬──────────┘      └────────┬──────────┘
         ▼
┌──────────────────────────────────────────────┐
│ 审批门 → 真实 CMMS 写（前置 auth/审计/幂等/   │
│ 限流/补偿 等 blocker，见 NEXT_PHASES.md）      │
└──────────────────────────────────────────────┘
```

关键点：**工具、分析、RAG、审批、trace 五层 Harness 在 target 中保持不变**，只有
planner / synthesizer 被替换为 LLM。

## 3. 目录结构

```text
.
├─ scripts/
│  ├─ generate_synthetic_data.py   # 生成合成数据 + ground truth
│  ├─ load_database.py             # 导入 SQLite
│  └─ run_evaluation.py            # 跑离线评估
├─ src/
│  ├─ contracts/                   # Pydantic 契约（叶子层）
│  ├─ config.py                    # 环境配置
│  ├─ db/                          # schema + 只读 repository
│  ├─ tools/                       # 只读工具（typed）
│  ├─ analytics/                   # 趋势 / 异常 / summary
│  ├─ rag/                         # 分块 / 关键词检索
│  ├─ agent/                       # 状态机 / 审批 / trace
│  ├─ evaluation/                  # 离线评估
│  └─ api/                         # FastAPI
├─ ui/streamlit_app.py             # Streamlit
├─ data/raw/                       # 生成的 CSV
├─ data/docs/                      # 虚构维修文档（5 篇）
├─ data/industrial.db              # SQLite
├─ tests/                          # 66 个用例
├─ Dockerfile
└─ docker-compose.yml
```

注意：**没有 CLI 入口**。仅有 `scripts/*.py` 三个可执行脚本（数据生成、入库、评估），
Agent 的交互入口是 API 与 Streamlit UI。

## 4. 数据模型

### 4.1 SQLite 表（`src/db/schema.py`）

| 表 | 主键 | 关键字段 |
|---|---|---|
| assets | asset_id | asset_name, asset_type, line, department, manufacturer, model, install_date, criticality, status |
| work_orders | wo_id | asset_id, created_at, completed_at, wo_type, priority, symptom, diagnosis, action_taken, downtime_min, status |
| meter_readings | reading_id | asset_id, timestamp, cycle_count, runtime_hours, temperature_c, pressure_bar, vibration_rms, current_a |
| maintenance_plans | plan_id | asset_id, task_group_id, trigger_type, interval_value, interval_unit, last_completed_at, next_due_at, active |
| task_groups | (task_group_id, task_seq) | task_text, safety_critical |
| parts | part_id | part_name, category, unit_cost, stock_qty, reorder_point |
| asset_parts | — | asset_id, part_id, quantity, relationship_type |
| part_usage | event_id | wo_id, asset_id, part_id, quantity, timestamp |
| events | event_id | asset_id, timestamp, event_type, severity, description |

`ground_truth_failures.csv` 不入库：它是评估专用，运行时不可被 agent 读取。

### 4.2 原始文件（`data/raw/`）

- assets.csv, work_orders.csv, meter_readings.csv, maintenance_plans.csv,
- task_groups.csv, parts.csv, asset_parts.csv, part_usage.csv, events.csv,
- ground_truth_failures.csv（评估专用）

## 5. 契约层（`src/contracts/`）

| 文件 | 实体 | 说明 |
|---|---|---|
| common.py | Priority, ToolErrorCode, ToolError, ToolResult, ActionType, ApprovalStatus, ProposedAction, utcnow | 跨层工具/审批契约 |
| assets.py | AssetType, AssetCriticality, AssetStatus, Asset | 设备 |
| work_orders.py | WorkOrderType, WorkOrderStatus, WorkOrder, WorkOrderSearchRequest, WorkOrderSearchResult | 工单 |
| meter.py | SignalName, MeterReading, MeterSummaryRequest, SignalSummary, MeterSummary | 计量 |
| evidence.py | EvidenceSourceType, EvidenceItem | 证据 |
| rag.py | DocumentChunk, RetrievalResult | RAG |
| agent.py | Confidence, Hypothesis, AgentStatus, ToolCallTrace, TraceRecord, AgentState | 状态机 / 假设 / trace |
| evaluation.py | EvalScenario, EvalResult, MetricsSnapshot | 评估 |

### 关键契约细节

- `ToolResult[T]`：`ok`、`data`、`error`、`empty`；`success()` / `failure()` 工厂方法。
- `ToolError`：`code`（enum）、`message`、`retryable`、`context`。
- `ProposedAction`：`action_type`、`asset_id`、`summary`、`priority`、`status`（默认 `PENDING_APPROVAL`）、`created_at`（UTC，默认 `utcnow`）、`approved_at`（可空，approve 时写入时区感知 UTC 时间）、`approved_by`（approve/reject 时写入操作者；reject 会把 `approved_at` 清空为 `None`）。
- `Hypothesis`：`cause`、`confidence`、`supporting_evidence_ids`、`contradicting_evidence_ids`、`rationale`、`recommended_checks`。
- `EvidenceItem`：`source_type`、`source_id`、`asset_id`、`summary`、`timestamp`、`citation`、`metadata`。source-id 是稳定可引用 id，但引用存在 ≠ grounding 充分（见第 11.1 节）。
- `AgentState`：`request_id`、`user_question`、`asset_id`、`evidence`、`tool_calls`、`hypotheses`、`pending_action`、`status`、`final_answer`。

## 6. 配置（`src/config.py`）

`Settings` 从环境变量读取，密钥用 `SecretStr`（repr 隐藏）。

| 环境变量 | 字段 | 默认 |
|---|---|---|
| PROJECT_NAME | project_name | industrial-maintenance-agent |
| DATA_DIR | data_dir | data |
| DB_PATH | db_path | data/industrial.db |
| TRACES_DIR | traces_dir | traces |
| LLM_MODEL | llm_model | deepseek-chat |
| LLM_BASE_URL | llm_base_url | None |
| LLM_API_KEY | llm_api_key | None |
| DEFAULT_WORK_ORDER_LOOKUP_DAYS | default_work_order_lookup_days | 30 |

`get_settings()` 是 `lru_cache` 单例。

注意：`LLM_*` 三个字段是**为未来 LLM 集成预留的声明**，当前确定性 baseline 不读取、不使用它们。

## 7. 数据生成（`scripts/generate_synthetic_data.py`）

- 固定 seed、幂等、可复现。
- 6 种失效模式，注入到最近窗口：
  - A001 lubrication_degradation：温度↑、振动微↑、摩擦类工单
  - A006 position_sensor_instability：振动毛刺、间歇读数类工单
  - A011 bearing_degradation：振动↑、温度↑、轴承类工单
  - A015 cooling_degradation：温度↑、过热类工单
  - A016 hydraulic_leakage：压力↓、泄漏类工单
  - A025 normal_or_false_alarm：孤立毛刺 + 误导工单
- 数据瑕疵：~1.5% 缺失、重复读数、误导工单、延迟完工。

## 8. 数据层（`src/db/`）

- `schema.py`：DDL。
- `repository.py`：`Repository`，只读连接（`mode=ro`），参数化 SQL。
  - `get_asset(asset_id) -> Optional[Asset]`
  - `list_assets(limit) -> List[Asset]`
  - `search_recent_work_orders(asset_id, days, limit) -> List[WorkOrder]`
  - `get_meter_history(asset_id, start, end, limit) -> List[MeterReading]`
  - `get_recent_meter_readings(asset_id, days, limit) -> List[MeterReading]`

「最近 N 天」以数据内 `MAX(timestamp)` 为基准，避免合成数据因「当前时间」晚于数据而查空。

## 9. 工具层（`src/tools/`）

每个工具返回 `ToolResult`；参数非法返回 `INVALID_ARGUMENT`，上游失败返回 `UPSTREAM_UNAVAILABLE`。

- `get_asset_tool(repo, asset_id)`
- `list_assets_tool(repo, limit)`
- `search_recent_work_orders_tool(repo, WorkOrderSearchRequest)`
- `get_meter_history_tool(repo, asset_id, days, limit)`

### 9.1 ToolRegistry（`src/agent/tools.py`）

`ToolRegistry` 当前注册 4 个工具：`get_asset`、`search_recent_work_orders`、
`get_meter_history`、`search_docs`，并为它们提供 JSON schema（对齐 OpenAI
function-calling 格式）。`list_assets_tool` 可独立调用，但**尚未进入 registry**。

### 9.2 schema 声明 vs 强制（重要区分）

- **声明（declared）**：`ToolRegistry.schemas()` 输出每个工具的名称 / 描述 / 参数 JSON schema。这些 schema 是为未来 LLM tool-calling 预备的「可选项清单」。
- **未强制（not enforced）**：当前确定性 pipeline 的 `planner.plan()` **不读取 schema**，而是硬编码固定 4-tool plan；`ToolRegistry.call()` 也只是按名字 dispatch，**不依据 schema 校验参数**。参数合法性的运行时强制发生在工具 / repository 层（Pydantic 校验 + `INVALID_ARGUMENT`）。

因此：schema 是「描述性元数据」，不是当前运行时的「选择约束」或「参数校验器」。

## 10. 分析层（`src/analytics/`）

- `trend.compute_meter_summary(readings, MeterSummaryRequest) -> MeterSummary`
  - recent = 最近 7 天；baseline = 之前 `days` 天
  - 每信号算 `baseline_mean`、`recent_mean`、`relative_change_pct`、`trend_slope`、`missing_count`
- 空输入（`readings=[]`）返回带类型的 `MeterSummary`：`signals={}`，`baseline_days` 来自请求，`recent_days` 保持固定 7 天窗口，不抛错。
- `anomaly`：`median_absolute_deviation`、`modified_zscore`、`rolling_zscore`、`flag_anomalies`

## 11. RAG 分块与检索器（`src/rag/`）

- `chunking.chunk_markdown(text, document, target_chars, overlap_chars) -> List[DocumentChunk]`：heading-aware，section 内滑动窗口切分，稳定 `chunk_id`。
- `chunking.load_documents(docs_dir)`：加载 `data/docs/*.md`（5 篇虚构文档）。
- `retriever.KeywordRetriever`：倒排索引 + 词重叠打分；`search(query, top_k) -> RetrievalResult`。

### 11.1 RAG 限制（准确口径）

1. **不是 BM25、不是向量检索、不是 hybrid RAG**。实现是 token-overlap 打分：用正则 `[a-z0-9]+` 把 query 与 chunk 文本都切成 ASCII 字母数字 token（小写），按「共现 token 数」计分，排序取 top-k（并列时按 `chunk_id` 稳定排序）。没有 idf / 长度归一化（非 BM25），没有 embedding / 相似度（非向量），因此也不是混合检索。
2. **tokenizer 仅匹配 ASCII 字母数字**：`[a-z0-9]+` 无法切分中文等非 ASCII 文本。当前虚构文档为英文，故可工作；换非英文语料需换 tokenizer / 检索后端。
3. **检索结果不参与根因打分**：`search_docs` 的结果会被 `executor` 转成 `EvidenceItem(source_type=DOCUMENT, source_id=chunk_id)` 放入 `state.evidence`，但 `synthesizer._rank()` 只使用**工单症状文本 + meter 信号相对变化**打分；DOCUMENT 证据**不影响** root-cause 排名。检索文档只是被「引用」（出现在 `supporting_evidence_ids` 里），不驱动结论。
4. 结论：**claim grounding 弱**。假设上的 source-id 引用是「可追溯」，不是「文档支撑了判断」。

边界：当前库存 / 最新读数走 SQL；手册 / SOP 走 RAG。

## 12. Agent 层（`src/agent/`）

### 12.1 流程

```text
interpret（正则解析资产 A\d{3}）
  → plan（固定 4 个只读工具）
  → execute（调工具、记录 trace、转证据）
  → synthesize（算 meter summary、检索 docs、生成假设、提 action）
  → trace 落盘
```

### 12.2 state / node / edge 语义（准确口径）

- **State**：单一 `AgentState` 对象，`runner.run()` 里 `AgentState(request_id=..., user_question=...)` 新建，随后**原地可变**地贯穿各阶段；不是不可变状态快照链，也不是图数据库节点。
- **Node（阶段函数）**：`planner.interpret` / `planner.plan` / `executor.execute` / `synthesizer.synthesize` 是普通函数，各自只改传入的 `state`。
- **Edge（控制流）**：线性串行，由 `runner.run()` 顺序调用；不是图结构，没有分支 / 回边 / 重试边。
- **状态值（`AgentStatus`）**：声明为 `INITIALIZED → RESOLVED → PLANNED → EXECUTED → SYNTHESIZED → COMPLETE`（另有 `ERROR`）。**实际发出的状态**：`INITIALIZED`（新建）→ `RESOLVED`（interpret 命中资产）→ `PLANNED`（plan 返回）→ `EXECUTED`（execute 完成）→ `COMPLETE`（synthesize 收尾）；任一阶段异常则置 `ERROR`。`SYNTHESIZED` 是**声明的枚举值但当前确定性路径未发出**（synthesize 直接置 `COMPLETE`）。

一句话：当前是「typed state + linear orchestration」，不是显式状态机或 LangGraph 图；合法迁移显式化属于 P0，LangGraph 迁移是条件化后续项（见 `NEXT_PHASES.md`）。

### 12.3 分类逻辑（`synthesizer.py`，确定性 baseline）

1. 汇总 WO 症状文本 + meter summary 的信号相对变化。
2. 用 `MODE_KEYWORDS` 关键词命中 + 信号 boost 给 6 种模式打分。
3. 取 top-3 生成 `Hypothesis`，`cause` 用人类可读标签。
4. 非 normal 模式时生成 `ProposedAction(CREATE_WORK_ORDER)`，状态 `PENDING_APPROVAL`。

`_rank()` 只消费 `wo_text`（工单证据）+ `temp/pressure/vibration` 相对变化；DOCUMENT 证据不进入打分。

### 12.4 请求 ID 策略（`request_id.py`）

- request id 兼作 trace 文件基名与内存审批表 key，因此强制安全字符集：`^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`。
- 额外拒绝 Windows 保留设备名（`CON` / `PRN` / `AUX` / `NUL` / `COM1-9` / `LPT1-9`），避免写出 `CON.json` 等非法文件。
- 三个边界统一校验：`AgentRunner.run`、FastAPI 路由、`TraceStore.save/load`（`request_id_path` 做 resolve + 包含性检查，阻止路径穿越）。
- 非法 ID 直接抛 `InvalidRequestIdError`（API 层转 HTTP 400），不静默改写。

### 12.5 审批门（`policy.py`）

- `approve_action(action, by)` / `reject_action(action, by)`：迁移 `ApprovalStatus`。
- `execute_pending_action(state)`：非 `APPROVED` 直接 `raise PermissionError`。
- `approve` 写入 `approved_by` 与时区感知的 `approved_at`（UTC）；`reject` 写入 `approved_by` 并把 `approved_at` 清空为 `None`。
- v0 无外部动作：`execute_pending_action` 只是「审批通过后返回该 action」的强制边界，不做任何 CMMS 写库或外部副作用。
- 审批状态是进程内 / 会话内内存决策：不持久化到磁盘或外部系统，重启后不保留。

### 12.6 Trace（`tracing.py`）

- `TraceStore`：按 `request_id` 写 JSON，`load()` 回读，`list()` 列出；保存/加载均走 `request_id_path` 的校验与路径包含检查。
- 检查范围：trace 记录工具调用、证据、假设与最终状态，可加载和查看；**当前没有重新执行历史请求的 replay 引擎**；审批决策（approve/reject）是内存态，也不落盘。
- `to_trace_record(state, latency)`：把 `AgentState` 转 `TraceRecord`。

### 12.7 memory 术语（准确口径）

- **没有 memory / 长程记忆**：无对话历史、无跨请求状态累积、无向量记忆库。
- **单次运行**：每个请求新建 `AgentState`，运行结束即弃；唯一留存的是 `traces/` 下的最终 JSON `TraceRecord`（快照，供检查，非执行日志）。
- **没有 checkpoint / resume**：运行不可暂停后恢复。
- **没有 replay**：trace 可读不可重放。
- 面试时请避免用「memory」「checkpoint」「replay」「audit」描述当前实现；它们是 target（`NEXT_PHASES.md`）中未实现的项。

### 12.8 Runner（`runner.py`）

- `AgentRunner.run(question, request_id?) -> AgentState`：编排全流程，异常捕获降级为 `ERROR`；结束后 `self.traces.save(...)` 落盘。

## 13. 评估层（`src/evaluation/`）

- `scenarios.build_scenarios()`：30 个场景（25 资产 + missing / ambiguous / prompt-injection / duplicate / unauthorized-write）。
- `metrics.compute_metrics(scenarios, results)`：7 个质量指标，另含 `total_scenarios` 场景总数。
- `runner.run_evaluation(repo, traces_dir, report_path)`：跑场景、算指标、写报告。

### 13.1 指标定义与「代理 / 静态 / 循环」口径

| 指标 | 计算 | 口径 |
|---|---|---|
| asset resolution accuracy | 解析出的资产 id 是否等于期望（分母仅统计 `expected_asset_id` 非空的场景） | 确定性正则解析，非模型能力 |
| root-cause top-1 / top-3 | 期望失效模式是否在 top-1 / top-3 假设里 | **circular**：规则打分器的 `MODE_KEYWORDS` / 信号 boost 与 ground truth 失效模式同源编写，合成数据上必然高分 |
| evidence recall | 召回的证据 id 占 ground-truth 相关证据的比例（交集 / ground-truth 集） | **真实、可解读**，当前 0.3698 |
| tool selection accuracy | `required_tools ⊆ tools_called` | **static / proxy**：固定 4-tool plan 恒为 required_tools 超集，恒为 1.0 |
| safety gate compliance | 所有 proposed action 是否仍 `PENDING_APPROVAL`（未自动执行） | **静态门态检查**，不是执行级安全证明（v0 本就不做外部写） |
| recovery rate | 错误/对抗场景是否按预期状态处理（missing/ambiguous → error；unauthorized_write → PENDING_APPROVAL；其余 → complete） | 确定性分支断言，**proxy** |

方法学细节与指标陷阱的完整讨论见 `EVALUATION_METHODOLOGY.md`。

## 14. API 接口文档

Base：`http://127.0.0.1:8000`，交互式文档 `/docs`。当前 API **无认证、无结构化应用日志**；
`pending` 审批表是 `create_app()` 内的进程内 `dict`，重启即丢、多 worker 不共享。

### GET /health

返回 `{"status": "ok"}`。

### GET /assets/{asset_id}

- 200：`Asset`
- 404：`{"detail": "asset not found"}`

```json
{
  "asset_id": "A001",
  "asset_name": "Hydraulic Press A001",
  "asset_type": "hydraulic_press",
  "line": "Line 1",
  "department": "Stamping",
  "manufacturer": "Nordvik",
  "model": "MOD-101",
  "install_date": "2024-09-08",
  "criticality": "medium",
  "status": "active"
}
```

### GET /work-orders?asset_id=&days=&limit=

- Query：`asset_id`（必填）、`days`（1-365，默认 30）、`limit`（1-100，默认 20）。
- 200：`WorkOrder[]`（无结果返回空数组）。

### GET /meter-summary?asset_id=&days=

- Query：`asset_id`（必填）、`days`（默认 30）。
- 200：`MeterSummary`；404：无读数。

```json
{
  "asset_id": "A001",
  "baseline_days": 30,
  "recent_days": 7,
  "computed_at": "2026-08-20T00:00:00Z",
  "signals": {
    "temperature_c": {
      "signal": "temperature_c",
      "baseline_mean": 65.1,
      "recent_mean": 71.3,
      "relative_change_pct": 9.5,
      "trend_slope": 0.31,
      "baseline_window_days": 30,
      "recent_window_days": 7,
      "missing_count": 0
    }
  }
}
```

### POST /agent/query

请求体：

```json
{"question": "A001 stopped this week. Check the recent trend.", "request_id": "optional"}
```

- `request_id` 可选；传入时必须通过安全字符集与 Windows 保留名校验，否则 HTTP 400；缺省时服务端生成 `uuid4().hex`。

返回 `AgentState`：

```json
{
  "request_id": "abc123",
  "user_question": "A001 stopped this week. Check the recent trend.",
  "asset_id": "A001",
  "evidence": [],
  "tool_calls": [],
  "hypotheses": [
    {
      "cause": "Lubrication degradation",
      "confidence": "high",
      "supporting_evidence_ids": ["WO-0001", "meter_summary:A001"],
      "contradicting_evidence_ids": [],
      "rationale": "temperature is +9.5% vs baseline",
      "recommended_checks": ["Inspect lubrication pressure and filter condition"]
    }
  ],
  "pending_action": {
    "action_type": "CREATE_WORK_ORDER",
    "asset_id": "A001",
    "summary": "Inspect for Lubrication degradation",
    "priority": "high",
    "status": "PENDING_APPROVAL"
  },
  "status": "complete",
  "final_answer": "..."
}
```

### POST /actions/{action_id}/approve 与 /reject

- `action_id` 即 `/agent/query` 返回的 `request_id`。
- 非法 / 保留名 `action_id`（如 `bad.id`、`CON`）→ HTTP 400，`detail` 为校验信息。
- 200：迁移后的 `ProposedAction`（`APPROVED` / `REJECTED`）。
- 404：action 不存在（或尚未在本次进程内产生 pending action）。
- approve 响应含 `approved_by`（`"api"`）与时区感知的 `approved_at`；reject 响应含 `approved_by` 且 `approved_at` 为 `null`。
- 注意：approve/reject 只改变进程内 `pending` 表里的状态，**不触发任何外部写**。

### GET /traces/{request_id}

- 200：`TraceRecord`
- 400：非法 / 保留名 `request_id`
- 404：trace 不存在

```json
{
  "request_id": "abc123",
  "question": "A001 stopped this week.",
  "asset_id": "A001",
  "tool_calls": [{"tool": "get_asset", "args": {"asset_id": "A001"}, "status": "success", "result_count": 1, "latency_ms": 0}],
  "evidence_ids": ["A001", "WO-0001"],
  "hypothesis_causes": ["Lubrication degradation"],
  "pending_action_type": "CREATE_WORK_ORDER",
  "total_latency_ms": 12,
  "status": "complete"
}
```

## 15. UI（`ui/streamlit_app.py`）

三个 tab：

- Agent：输入问题 → 跑 agent → 显示答案 / 假设 / 证据 / 审批按钮。
- Asset Explorer：查资产 + 近期工单。
- Trace Inspector：选择 request 查看 trace。

审批决策只存在 `st.session_state`（当前会话内存）：普通 widget rerun 后仍然可见，但进程重启或新会话不保留，也不触发任何外部执行（v0 无外部动作）。

## 16. Docker（状态：文件存在，运行时验证 pending）

- `Dockerfile`：基于 `python:3.11-slim`，安装依赖、生成数据、删除 ground truth、`uvicorn` 启动。
- `docker-compose.yml`：`api`（8000）+ `ui`（8501）。

```bash
docker compose up --build
```

**状态说明**：`Dockerfile` 与 `docker-compose.yml` **文件已存在且内容已评审**，但镜像构建与容器运行**尚未验证**（本地 daemon 不可用）。因此「Docker 可用」是未验证状态，面试时不要声称已验证运行。

## 17. 运行方式

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python scripts\generate_synthetic_data.py
.\.venv\Scripts\python scripts\load_database.py
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python scripts\run_evaluation.py
.\.venv\Scripts\python -m uvicorn src.api.main:app --reload
.\.venv\Scripts\python -m streamlit run ui/streamlit_app.py
```

## 18. 测试与评估结果

- `pytest`：66 个用例。
- 离线评估：30 场景、7 项质量指标，另含 `total_scenarios` 场景总数。
- 当前指标：root-cause top-1/top-3 = 1.0（circular）、proposal gate-state compliance = 1.0（静态）、tool selection = 1.0（static）、recovery = 1.0（proxy）、evidence recall = 0.3698（真实）。

口径详见第 13.1 节与 `EVALUATION_METHODOLOGY.md`。

## 19. 安全与权限模型

### 19.1 已实现（有回归测试）

- 只读工具自动执行；写类动作只生成 `ProposedAction`，非 `APPROVED` 执行会抛 `PermissionError`。
- ground truth 不入库、不进 Docker 镜像、不暴露给 agent。
- request id 严格校验（`^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`）+ Windows 保留名拒绝 + trace 路径包含，在 API / `AgentRunner` / `TraceStore` 三处强制。
- 审批记录 `approved_by` 与时区感知的 `approved_at`；reject 清空 `approved_at`。
- v0 明确无外部写动作（`execute_pending_action` 只是门禁边界，不触发 CMMS 变更）。
- `LLM_API_KEY` 用 `SecretStr` 隐藏，`.env` 不入库（`.gitignore`）。

### 19.2 边界与未实现（勿过度声明）

- 当前确定性 baseline 把 retrieved 文档当 data；这**不是**未来 LLM 集成后的 prompt-injection 防御证明。
- 以下为真实 CMMS 写操作前的硬阻塞项（详见 `NEXT_PHASES.md` 与 `SAFETY_AND_THREAT_MODEL.md`）：身份认证 / 授权、持久化审批审计、终态状态转移、多进程共享状态、冲突 / 幂等、trace 访问 / 脱敏 / 保留、请求限制 / 限流、执行回执 / 补偿、执行级安全评估。v0 不含这些能力。

## 20. 扩展点

- 接 LLM：替换 `planner` / `synthesizer`，工具 schema 已备好（`ToolRegistry.schemas()`）。
- 新工具：在 `src/db/repository.py` 加查询，在 `src/tools/` 包装，在 `ToolRegistry` 注册。
- parquet：需先加入 `pyarrow` 依赖，再改 `meter_readings` 读写。
- CI：跑 pytest + 评估门禁（目前无 CI）。
- 可选 LangGraph：迁移 `runner.py` 的显式状态机。

详见 `NEXT_PHASES.md`。

## 21. 文档索引（canonical docs）

- `CAPABILITY_MATRIX.md` — 能力矩阵（可演示/不可演示的清单）
- `EVALUATION_METHODOLOGY.md` — 评估方法学与指标口径
- `SAFETY_AND_THREAT_MODEL.md` — 安全与威胁模型
- `INTERVIEW_GUIDE.md` — 面试讲解指南
- `NEXT_PHASES.md` — 后续阶段设计
- `EVALUATION_REPORT.md` — 离线评估原始报告
- `PLAN_8H.md` / `WORKLOG.md` / `WORKLOG_DETAILS.md` — 开发计划与工作日志
