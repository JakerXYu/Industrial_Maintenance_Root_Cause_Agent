# Industrial Maintenance / Root-Cause Agent（工业维护根因分析 Agent）

> 面向 Agent 工程师面试的作品集项目：演示「确定性 Harness 先行、LLM 后置」的
> agent 系统工程范式。当前交付是一个**确定性、无 LLM 的根因分析 baseline**，
> 不是生产系统。

## 定位（Positioning）

**是什么**：一条可复现、可测试的确定性 agent 管线，端到端打通
`typed read-only tools → 确定性时间序列分析 → document retrieval / RAG scaffold → 审批门 → trace/离线评估`，
用规则基线跑通全链路并产出可机检的指标。

**不是**（面试时勿过度声明）：

- 不是 **production-ready**：无认证、无审批审计、无结构化应用日志、无 CI，审批是进程内内存态。
- 不是 **autonomous agent**：planner / synthesizer 是确定性规则，不接任何模型。
- 当前只是 **document retrieval / RAG scaffold**：检索是 token-overlap 关键词检索（非 BM25、非向量、非混合检索），且检索文档不参与根因打分。
- 不是 **evidence-grounded**：假设带 source-id 引用，但检索文档不驱动推理，claim grounding 弱（见「口径警示」）。

一句话：**造一个可验证、可观测、可审批的 Agent Harness，把不可验证的 LLM 留作后置插件。**

## 现状架构 vs 目标架构

### Current（已实现，确定性 baseline）

```text
用户问题
  └─ interpret      正则解析 asset_id（A\d{3}），失败→ ERROR
  └─ plan           固定 4 个只读工具
      ├─ get_asset
      ├─ search_recent_work_orders (days=30, limit=20)
      ├─ get_meter_history        (days=37, limit=5000)
      └─ search_docs              (top_k=3, token-overlap document retrieval)
  └─ execute        逐工具调用 + 逐调用 trace + 转 EvidenceItem
  └─ synthesize     规则打分（WO 症状关键词 + meter 信号相对变化）
                     → top-3 Hypothesis + ProposedAction(PENDING_APPROVAL)
  └─ trace          落一份 JSON TraceRecord（无 checkpoint / replay）
审批门              进程内内存 approve/reject，无外部写
```

### Target（未实现，设计见 `docs/NEXT_PHASES.md`）

```text
用户问题
  └─ bounded runtime 合法状态迁移 + deadline / retry / step budget
  └─ LLM planner     仅可提出已注册、通过 schema 校验的 read tool calls
  └─ tool gateway    统一校验、超时、重试、调用账本与结果规范化
  └─ BM25 retrieval  结构化 evidence + unique IDs
  └─ LLM synthesizer structured claims → citation verifier / abstention
  └─ runtime store   checkpoint + durable action proposal / audit events
```

关键点：保留 typed read-only domain tools 与确定性分析；LLM 只是可替换 policy。目标阶段仍不做真实 CMMS mutation，真实写入继续受 `docs/SAFETY_AND_THREAT_MODEL.md` 的 blocker 约束。

## 能力摘要

| 层 | 交付物 | 状态 |
|---|---|---|
| 契约 contracts | Pydantic 模型（asset / work order / meter / evidence / RAG / agent / evaluation） | 完成 |
| 数据 data | 25 资产、180 天、2h 采样、6 种失效模式 + ground truth | 完成 |
| 数据层 db | SQLite `mode=ro` + 参数化 SQL | 完成 |
| 工具 tools | typed read-only tools，统一返回 `ToolResult` | 完成（registry 注册 4 个） |
| 分析 analytics | trend / anomaly / meter summary（确定性） | 完成 |
| Document retrieval / RAG scaffold | heading-aware 分块 + token-overlap 关键词检索 | 部分完成（无 LLM，文档不参与根因打分） |
| Agent | typed state + 线性流程 + 审批门 + trace | 部分完成（无显式 graph / checkpoint / recovery） |
| 评估 evaluation（Track A） | 30 个合成场景 + 7 项指标（另含场景总数） | 部分完成（回归自检，非泛化证明） |
| 评估 evaluation（Track B） | UCI #447 外部真实传感器：摄取/特征/条件分类/held-out/typed 证据契约 | 完成（仅条件分类与证据契约，非 RCA） |
| API / UI | FastAPI + Streamlit | 完成 |
| Docker | Dockerfile + docker-compose.yml | PARTIAL：历史 base 镜像曾通过本地健康检查；当前 Track B 依赖镜像因 daemon 不可用未重建，Compose config 已通过 |
| LLM / CI / 结构化应用日志 / 认证 | — | 未实现 |

## Evaluation Tracks（评估双轨）

- **Track A — Controlled Synthetic Agent Evaluation**（受控合成 Agent 评估）：25 资产、180 天、
  30 场景、7 项指标，验证「确定性基线端到端跑通 + 回归自检」；但 top-k 与合成数据同源，属循环验证，
  不能外推真实数据。
- **Track B — External Real-Sensor Diagnostic Evaluation**（外部真实传感器诊断评估），只展示：

  - Dataset：UCI Hydraulic Systems
  - Data：2205 cycles，14 physical sensors，1–100 Hz
  - Split：profile-group-held-out
  - Results：Cooler Macro-F1 **1.000**；Valve Macro-F1 **0.5692**

> **Caveat（紧接的边界说明）：** Cooler perfect separability is specific to the current
> stable-regime benchmark setup and is not an end-to-end Agent accuracy result.
>
> 中文解释：Cooler 的完美可分性只针对当前基准设定（stable-regime-only、56 维统计特征、
> profile-group-held-out 划分），并不是端到端 Agent 准确率。

口径一句话（面试统一引用）：

> The external hydraulic benchmark evaluates the real-sensor diagnostic evidence layer and its integration with the Agent evidence contract; it does not measure end-to-end root-cause-agent accuracy.
>
> 中文解释：Hydraulic Systems 外部 Benchmark 验证的是真实传感器条件下的诊断证据层及其与
> Agent Evidence Contract 的集成，而不是完整端到端 Root-Cause Agent 的准确率。

Track A 详见 `docs/EVALUATION_METHODOLOGY.md` 与 `docs/EVALUATION_REPORT.md`；Track B 详见
`docs/benchmarks/HYDRAULIC_SYSTEMS_BENCHMARK.md` 与生成报告
`docs/EVALUATION_REPORT_EXTERNAL_HYDRAULIC.md`。两轨无数据重叠；Track B classifier harness 独立，
evidence integration 有意复用共享 `AgentState` / `EvidenceItem` contracts。结果不能互相代替。

## 代表性演示路径

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python scripts\generate_synthetic_data.py   # 可复现数据 + ground truth
.\.venv\Scripts\python scripts\load_database.py             # 入库
.\.venv\Scripts\python -m pytest                            # 114 passed
.\.venv\Scripts\python scripts\run_evaluation.py            # 30 scenarios → 报告
.\.venv\Scripts\python -m uvicorn src.api.main:app --reload # http://127.0.0.1:8000/docs
```

一次代表性请求（详见 `docs/HANDBOOK.md` 第 14 节 API 文档）：

```text
POST /agent/query  {"question": "A001 stopped this week. Check the recent trend."}
  → AgentState: asset_id=A001, top hypothesis "Lubrication degradation",
                pending_action=PENDING_APPROVAL
POST /actions/{request_id}/approve
  → ProposedAction(status=APPROVED, approved_by="api", approved_at=<tz-aware UTC>)
GET  /traces/{request_id}
  → TraceRecord（tool_calls / evidence_ids / hypothesis_causes）
```

## 实测结果与口径警示（Track A 合成数据）

30 个合成场景、114 个测试全绿。指标（`docs/EVALUATION_REPORT.md`
为原始报告，仅覆盖 Track A）：

| 指标 | 值 | 口径警示 |
|---|---|---|
| asset_resolution_accuracy | 1.0 | 确定性正则解析，非模型能力 |
| root_cause_top1 / top3 | 1.0 | 规则打分器与 ground truth 同源注入，**circular** |
| tool_selection_accuracy | 1.0 | 固定 4-tool plan 恒为 required_tools 超集，**static / proxy** |
| safety_gate_compliance | 1.0 | 仅检查 proposal 仍为 `PENDING_APPROVAL`，**静态门态检查**，非执行级安全 |
| recovery_rate | 1.0 | 确定性分支上的状态断言，**proxy** |
| evidence_recall | **0.3698** | **真实、可解读**：gold event 证据当前不可达，且 WO 查询/转证据有窗口与数量限制 |

阅读姿势：**不要单独引用 top-k / tool / safety / recovery = 1.0**——在该确定性 + 合成数据设定下它们是静态 / 循环 / 代理指标；`evidence_recall = 0.3698` 暴露的是 events 工具缺失与 WO 证据覆盖不足。检索文档不参与根因打分是另一个独立的 grounding 缺陷。方法学与口径见 `docs/EVALUATION_METHODOLOGY.md`。

## 安全保证与非保证

**保证（已实现、有回归测试）**

- 只读工具自动执行；写类动作只产出 `ProposedAction`，非 `APPROVED` 执行抛 `PermissionError`（v0 无外部写路径）。
- request id 严格校验（`^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$` + Windows 保留名拒绝 + trace 路径包含），在 API / `AgentRunner` / `TraceStore` 三处强制。
- ground truth 不入库、不进镜像、不暴露给 agent。
- `LLM_API_KEY` 用 `SecretStr` 隐藏，`.env` 不入库。

**非保证（边界，勿过度声明）**

- 审批是**进程内 / 会话内内存态**：重启即丢、多 worker 不共享、无持久审计。
- 无认证 / 授权、无结构化应用日志、无限流、无执行回执 / 补偿；已有 JSON trace 只用于运行诊断。
- 确定性 baseline 把 retrieved 文档当 data，**不是** prompt-injection 防御证明（针对未来 LLM 集成）。
- 接真实 CMMS 写操作前仍有硬阻塞项，见 `docs/SAFETY_AND_THREAT_MODEL.md`。

## 快速开始

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
.\.venv\Scripts\python scripts\generate_synthetic_data.py
.\.venv\Scripts\python scripts\load_database.py
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python scripts\run_evaluation.py

# API (http://127.0.0.1:8000/docs)
.\.venv\Scripts\python -m uvicorn src.api.main:app --reload

# UI（另一个终端）
.\.venv\Scripts\python -m streamlit run ui/streamlit_app.py

# Docker（当前需先启动 daemon；Track B 依赖镜像尚未重建验证）
docker compose up --build
```

## 设计决策与非目标

**设计决策**

- **contracts 是叶子层**：只 import 兄弟契约 + stdlib / pydantic，永不 import 运行时层。
- **empty ≠ error**：`ToolResult.empty=True` 表示「成功但 0 行」；`ok=False` 才是真失败。
- **read 自由、write 审批**：`ProposedAction` 恒以 `PENDING_APPROVAL` 起步，未 APPROVE 不可执行。
- **typed everywhere / enums over strings**：模块边界用 Pydantic 契约，不传裸 dict。
- **raw sqlite3 + `mode=ro`**：Pydantic 已承担输出契约，无需 ORM。
- **keyword retriever 而非 embeddings / BM25**：v0 零外部依赖，检索后端可替换。
- **rule-based planner / synthesizer 作为 baseline**：LLM policy 后续接入，但不绕过 runtime、tool 和 evidence 契约。

**非目标**

- 不做通用维修聊天机器人。
- 不做多轮对话 / 长程 memory（当前为单次运行 `AgentState`）。
- 不做向量检索 / 重排（v0）。
- 不宣称生产可用、自治、或 evidence-grounded。

## 文档索引

面向最终用户：

- [`docs/USER_GUIDE_CN.md`](docs/USER_GUIDE_CN.md) — 中文用户指南（第一次使用者的操作手册）

权威文档（面试前必读）：

- [`docs/HANDBOOK.md`](docs/HANDBOOK.md) — 当前实现综合参考（本 README 的权威细节版）
- [`docs/CAPABILITY_MATRIX.md`](docs/CAPABILITY_MATRIX.md) — 能力矩阵
- [`docs/EVALUATION_METHODOLOGY.md`](docs/EVALUATION_METHODOLOGY.md) — 评估方法学与指标口径
- [`docs/SAFETY_AND_THREAT_MODEL.md`](docs/SAFETY_AND_THREAT_MODEL.md) — 安全与威胁模型
- [`docs/INTERVIEW_GUIDE.md`](docs/INTERVIEW_GUIDE.md) — 面试讲解指南
- [`docs/EXTERNAL_EVIDENCE_INTEGRATION.md`](docs/EXTERNAL_EVIDENCE_INTEGRATION.md) — Track B 诊断证据进入 Agent Evidence Contract 的边界
- [`PROJECT01_REVIEW_MERGED.md`](PROJECT01_REVIEW_MERGED.md) — 冻结版本外部评审合并稿

过程与规划：

- [`docs/EVALUATION_REPORT.md`](docs/EVALUATION_REPORT.md) — 离线评估原始报告（Track A）
- [`docs/EVALUATION_REPORT_EXTERNAL_HYDRAULIC.md`](docs/EVALUATION_REPORT_EXTERNAL_HYDRAULIC.md) — 外部液压基准原始报告（Track B，生成物）
- [`docs/benchmarks/HYDRAULIC_SYSTEMS_BENCHMARK.md`](docs/benchmarks/HYDRAULIC_SYSTEMS_BENCHMARK.md) — 液压系统外部基准权威说明（Track B）
- [`docs/NEXT_PHASES.md`](docs/NEXT_PHASES.md) — P0/P1/P2 路线图、验收标准与非目标
- [`docs/PLAN_8H.md`](docs/PLAN_8H.md) / [`docs/WORKLOG.md`](docs/WORKLOG.md) / [`docs/WORKLOG_DETAILS.md`](docs/WORKLOG_DETAILS.md) — 历史计划与工作日志
