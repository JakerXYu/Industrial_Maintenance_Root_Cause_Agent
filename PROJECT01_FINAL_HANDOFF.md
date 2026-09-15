# PROJECT01 FINAL HANDOFF — Industrial Maintenance / Root-Cause Agent（最终冻结 Portfolio v1.0）

> 本文是 Portfolio v1.0 的最终冻结交接稿，自洽、可独立交付。未来 ChatGPT 只会收到本文件，因此所有核心事实都写在本文件内，不依赖其他文档即可成立；仓库路径仅作为证据索引（evidence index）。
> 冻结定位：**Evidence-oriented Industrial Agent Harness**（证据导向的工业 Agent 脚手架）；**Deterministic Industrial Maintenance Root-Cause Analysis Baseline**（确定性工业维护根因分析基线）；**确定性 Harness 先行、LLM policy 后置**。
> 明确**不是**：Production RCA Agent、LLM Agent、Autonomous Agent、成熟 RAG。

---

## 1. 一页速览

项目是一个面向 Agent 工程师面试的作品集：一条**确定性、无 LLM 的工业维护根因分析 baseline**，定位为 Evidence-oriented Industrial Agent Harness。它要回答的不是「做一个维修聊天机器人」，而是「如何把一个概率模型放进一个可验证、可观测、可审批的确定性软件系统」：**LLM 不是 system of record**，真实状态由工具查、数值结论由代码算，LLM 只是未来后置的 policy 插件。

当前架构是一条可复现、可测试的确定性管线：typed read-only tools（get_asset / search_recent_work_orders / get_meter_history / search_docs）→ SQLite(mode=ro) → 确定性时间序列分析 → document retrieval / RAG scaffold → 人工审批门 → JSON trace / 离线评估。全链路无 LLM、无 LangGraph。

评估分双轨且互不替代：Track A 在 25 资产 / 180 天 / 30 个合成场景上跑 7 项指标，验证端到端跑通与回归自检；Track B 用 UCI #447 真实液压传感器做条件分类与诊断证据契约集成。

Top 3 价值：其一，契约先行、typed everywhere，模块边界清晰可测；其二，双轨评估诚实区分「循环 / 静态 / 代理指标」与「实际测得但仅属于 synthetic regression 的 evidence_recall=0.3698」，暴露缺陷而非美化；其三，安全边界清晰（read 自由、write 审批、v0 无外部写）。

Top 3 局限：其一，Track A 的 top1/top3=1.0 是循环验证，不能外推真实世界；其二，检索文档不参与根因打分，claim grounding 弱；其三，无 retry/timeout/checkpoint/resume/fallback，审批为进程内内存态，非生产可用。

---

## 2. 项目最终定位

**是什么（是什么 / What it is）**

- 中文：一个**可验证、可观测、可审批的确定性工业 Agent Harness**，端到端打通「typed read-only tools → 确定性时间序列分析 → document retrieval / RAG scaffold → 审批门 → trace / 离线评估」，用规则基线跑通全链路并产出可机检指标。
- English: A **reproducible, testable deterministic Agent harness** that wires typed read-only tools, deterministic time-series analytics, a document retrieval scaffold, a human approval gate, and trace/offline evaluation end to end, with a rule-based baseline and machine-checkable metrics.
- 一句话：**造一个可验证、可观测、可审批的 Agent Harness，把不可验证的 LLM 留作后置插件。**

**不是什么（What it is NOT — 面试时勿过度声明）**

- 不是 **Production RCA Agent**：无认证、无审批审计、无结构化应用日志、无 CI，审批是进程内内存态。
- 不是 **LLM Agent**：planner / synthesizer 是确定性规则，不接任何模型。
- 不是 **Autonomous Agent**：固定 plan、线性编排，无动态决策、无自愈。
- 不是 **成熟 RAG**：检索是 token-overlap 关键词检索（非 BM25、非向量、非混合、非重排），且检索文档不参与根因打分。

---

## 3. 为什么做这个项目

核心动机是演示工业场景下「Agent 系统性工程」而非「调 prompt」。链路遵循：

**Question → state → tools → evidence → hypothesis → approval → trace**

- **Question**：用户自然语言问题（如 "A001 stopped this week. Check the recent trend."）。
- **State**：单次运行的一个 `AgentState` 对象贯穿 interpret → plan → execute → synthesize。
- **Tools**：4 个 typed read-only 工具，查 SQLite 与文档。
- **Evidence**：工具结果转成带稳定 source-id 的 `EvidenceItem`。
- **Hypothesis**：规则打分器产出 top-3 `Hypothesis`，附 supporting/contradicting evidence ids。
- **Approval**：写类意图只产出 `ProposedAction(PENDING_APPROVAL)`，未审批不可执行。
- **Trace**：落一份 JSON `TraceRecord`，供可观测与离线诊断。

关键原则：**LLM 不是 system of record**——真实状态由工具查，数值结论由代码算，LLM（未来）只做推理与表达。当前用确定性规则基线先让外围的评估、安全、观测「可靠起来」，再接 LLM，从而能回答「接 LLM 后如何验证它没做错」。

---

## 4. 当前完整架构

### 4.1 Current（已实现，确定性 baseline）

```text
┌──────────────────────────────────────────────┐
│ Streamlit UI / FastAPI                        │
│ asset/task + review proposal + trace inspect  │
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
│ Typed Read Tools  │      │ Retrieval scaffold │
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

当前代码里**没有** CLI、**没有** LLM、**没有** LangGraph、**没有**图（graph）；只有 API、Streamlit UI 与 typed state + linear orchestration。

### 4.2 Future / Not Implemented（仅设计，未实现，见 `docs/NEXT_PHASES.md`）

```text
UI / API
  → bounded runtime（显式合法迁移、deadline、retry、step budget）
  → LLM policy（typed plan；只能提出已注册 read tool calls）
  → schema-enforced tool gateway（校验、超时、调用账本）
  → BM25 retrieval baseline + structured evidence
  → structured claims + citation verifier / abstention
  → 独立 runtime store（checkpoint、durable action proposal、audit events）
```

关键点：保留 typed read-only domain tools 与确定性分析；LLM 只是可替换 policy，不能绕过 runtime、tool、evidence、approval 契约。Target 仍不默认接真实 CMMS 写入。

---

## 5. Contracts-first Design（契约先行）

契约层是叶子层（`src/contracts/`）：只 import 兄弟契约 + stdlib / pydantic，永不 import 运行时层。所有跨模块边界用 Pydantic 契约，不传裸 dict。

| 契约 | 关键字段 | 源文件 |
|---|---|---|
| `AgentState` | `request_id` / `user_question` / `asset_id` / `evidence` / `tool_calls` / `hypotheses` / `pending_action` / `status` / `final_answer` | `src/contracts/agent.py` |
| `ToolResult[T]` | `ok` / `data` / `error` / `empty`；`success()` / `failure()` 工厂 | `src/contracts/common.py` |
| `ToolError` | `code`（enum）/ `message` / `retryable` / `context` | `src/contracts/common.py` |
| `EvidenceItem` | `source_type` / `source_id` / `asset_id` / `summary` / `timestamp` / `citation` / `metadata` | `src/contracts/evidence.py` |
| `Hypothesis` | `cause` / `confidence` / `supporting_evidence_ids` / `contradicting_evidence_ids` / `rationale` / `recommended_checks` | `src/contracts/agent.py` |
| `ProposedAction` | `action_type` / `asset_id` / `summary` / `priority` / `status`（默认 PENDING_APPROVAL）/ `created_at` / `approved_at` / `approved_by` | `src/contracts/common.py` |
| `ApprovalStatus` | enum：`PENDING_APPROVAL` / `APPROVED` / `REJECTED` | `src/contracts/common.py` |

**核心语义：empty ≠ error**

- `ToolResult.empty=True` 表示「成功但 0 行」（empty result）。
- `ok=False`（即 `ToolError` 被设置）才是真失败。
- 不变量：`ok is False` ⟹ `error` 设置且 `data=None`；`empty is True` ⟹ 调用成功但零行。
- 两者是两回事：空结果是正常业务含义，错误是调用失败。

---

## 6. Tool Layer（工具层）

**精确 4 个工具**（`ToolRegistry`，`src/agent/tools.py`）：

1. `get_asset` — 按 asset_id 返回单台资产元数据。
2. `search_recent_work_orders` — 检索资产近期工单（days 默认 30，limit 默认 20）。
3. `get_meter_history` — 检索资产近期计量读数。
4. `search_docs` — 关键词检索非结构化维修文档。

特性：

- **read-only + 参数化 SQL + `mode=ro`**：`src/db/repository.py` 用 raw `sqlite3` 只读连接、参数化 SQL；Pydantic 承担输出契约，无需 ORM。
- **schema 声明（declared）而非强制（not enforced）**：`ToolRegistry.schemas()` 输出每个工具的名称/描述/参数 JSON schema（为未来 LLM tool-calling 预备）；但当前 `planner.plan()` 硬编码固定 4-tool plan 不读 schema，`ToolRegistry.call()` 只按名字 dispatch、不依据 schema 校验参数。参数合法性运行时强制发生在工具 / repository 层（Pydantic + `INVALID_ARGUMENT`）。
- **无真实 LLM calling**：没有模型驱动的动态工具选择或调用；`list_assets_tool` 可独立调用但未注册进 registry。

---

## 7. Structured Data vs RAG（结构化数据 vs 检索）

**Exact quote（原文保留）**：

> RAG is for unstructured knowledge; structured tools are for transactional system state.

中文：RAG 用于非结构化知识；结构化工具用于事务性系统状态。

配套原则（原文）：

> LLM 不是 system of record。（The LLM is a probabilistic reasoning component inside a deterministic software system.）

**DB vs docs 边界**：当前库存 / 最新读数 / 工单 → SQL（`mode=ro` 参数化查询）；手册 / SOP / troubleshooting / policy → RAG（`data/docs/*.md`，5 篇虚构文档）。

**当前实现（准确口径）**：

- 分块：`chunk_markdown`（heading-aware，section 内滑动窗口 + overlap，稳定 `chunk_id`）。
- 检索：`KeywordRetriever` = token-overlap 关键词检索（正则 `[a-z0-9]+` 切 ASCII token，按「共现 token 数」计分）。
- **不是 BM25、不是向量、不是 hybrid、不是 rerank**。
- **文档不参与根因打分**：`search_docs` 结果转成 `EvidenceItem(source_type=DOCUMENT)` 进 `state.evidence`，但 `synthesizer._rank()` 只消费「工单症状文本 + meter 信号相对变化」，DOCUMENT 证据不影响 root-cause 排名。

---

## 8. Evidence / Grounding（证据与依据）

两个必须分开说的概念：

1. **traceability ≠ grounding（可追溯 ≠ 依据充分）**：每条 `Hypothesis` 带 `supporting_evidence_ids` / `contradicting_evidence_ids`，source-id 可追溯，但这只表示「挂了证据引用」，不表示「文档/证据真正支撑了判断」。
2. **citation exists ≠ correct（引文存在 ≠ 引文正确）**：`citation_valid=12` 只验证 `citation` 字符串等于稳定 `source_id`（格式正确、可溯源）；不度量被引证据是否是对该 claim 而言正确/相关的证据（`citation_precision` 未计算）。

**Grounding 现状：弱 / 未度量**

- 检索文档不驱动推理，claim grounding 弱（装饰性 RAG）。
- `supporting_evidence_ids` 无差别挂全部证据（未逐 claim 对齐），meter 证据用单一 `meter_summary:{asset_id}` 造成重复证据 id。
- `semantic_unsupported_claim_rate` = `not_measured_no_entailment_annotations`（**未度量**，因为没有独立 entailment 标注，不是 0，也不是「已通过」）。

---

## 9. Safety / Human Approval（安全与人工审批）

- **read 自由、write 提案**：只读工具自动执行；写类意图只产出 `ProposedAction`，恒以 `PENDING_APPROVAL` 起步。
- **pending 不可执行**：`execute_pending_action(state)` 对非 `APPROVED` 直接抛 `PermissionError`；v0 无外部写路径（`execute_pending_action` 只是门禁边界，不触发任何 CMMS 变更）。
- **审批端点存在**：`POST /actions/{request_id}/approve` 与 `/reject` 迁移 `ApprovalStatus`；approve 写 `approved_by` + 时区感知 `approved_at`，reject 清空 `approved_at`。
- **静态安全代理**：`safety_gate_compliance=1.0` 只检查提案仍停在 PENDING 门态，是静态门态检查，不是执行级安全证明（v0 本就不做外部写）。
- **边界（勿过度声明）**：审批是进程内/会话内内存态，重启即丢、多 worker 不共享；无认证/授权、无持久审计、无限流；`approved_by` 硬编码；approve 后可再 reject（可逆、无终态）。真实 CMMS 写前有硬阻塞项（见 `docs/SAFETY_AND_THREAT_MODEL.md`）。

---

## 10. Agent Runtime（智能体运行时）

- **State + linear（typed state + 线性编排）**：单一 `AgentState` 对象在 `runner.run()` 中新建并原地可变贯穿 interpret → plan → execute → synthesize；`planner/executor/synthesizer` 是普通函数，各自只改传入 state；控制流由 runner 顺序调用，无分支/回边/重试边。
- **状态枚举**：`INITIALIZED → RESOLVED → PLANNED → EXECUTED → SYNTHESIZED → COMPLETE`（另有 `ERROR`）。实际发出：`INITIALIZED → RESOLVED → PLANNED → EXECUTED → COMPLETE`；`SYNTHESIZED` 是声明值但当前确定性路径未发出（synthesize 直接置 COMPLETE）。
- **不是 graph、不是 recovery**：无显式状态机、无 LangGraph 图。
- **无 retry / timeout / checkpoint / resume / fallback**：`runner` 的 try/except 只是异常降级为 `ERROR`（优雅错误处理），不是重试或恢复；trace 可读不可重放（无 replay）。`AgentState` 只承担单次运行 working state；无 conversation / summary / long-term memory。
- 这些项是 **frozen future（冻结未来项）**，仅见于 `docs/NEXT_PHASES.md` P0-3，当前一律不声明已实现。

---

## 11. Track A — 受控合成 Agent 评估

- **生成**：`scripts/generate_synthetic_data.py` 固定 seed、幂等，注入 6 种失效模式（lubrication_degradation / position_sensor_instability / bearing_degradation / cooling_degradation / hydraulic_leakage / normal_or_false_alarm），~1.5% 缺失、重复读数、误导工单、延迟完工。
- **规模**：25 资产、180 天、2h 采样。
- **价值**：验证「确定性基线端到端跑通 + 回归自检」，回答规则基线能否在受控合成数据上可复现地产出资产解析、根因 top-k、工具选择、证据召回、安全门态与优雅降级。**不**回答真实世界泛化。
- **30 场景**：25 个资产场景 + `missing_asset` / `ambiguous_asset` / `prompt_injection` / `duplicate_records` / `unauthorized_write`。

**精确 7 项指标结果表**（`docs/EVALUATION_REPORT.md`）：

| 指标 | 值 | 口径 |
|---|---|---|
| asset_resolution_accuracy | 1.0 | 确定性正则解析，非模型能力 |
| root_cause_top1 | 1.0 | **circular**（与 ground truth 同源注入） |
| root_cause_top3 | 1.0 | **circular**（同上） |
| tool_selection_accuracy | 1.0 | **static / proxy**（固定 4-tool plan 恒为 required_tools 超集） |
| safety_gate_compliance | 1.0 | **proposal-state / 静态门态检查**，非执行级安全 |
| recovery_rate | 1.0 | **graceful-error / proxy**（场景级终态断言，非重试/恢复） |
| evidence_recall | **0.3698** | **实际测得的 synthetic regression coverage gap；非现场数据指标** |

另含 `total_scenarios=30`（场景计数，不是第 8 项指标）。

**evidence_recall=0.3698 的成因**：gold `relevant_evidence_ids` 含 EV-* 事件 id，但系统**没有 events 工具**，事件证据永远不可达；WO 查询 days=30 / limit=20，且 executor 只取前 10 条（`src/agent/executor.py` `[:10]`）造成截断，大量 gold WO id 漏召回。检索 DOCUMENT 证据不增加 recall（recall 只取 gold 交集）。

**口径结论**：Track A 所有指标只能定位为**合成数据上的回归自检**，不对外宣称模型能力 / 生产可用性，**没有真实世界 RCA 准确率**。

---

## 12. Track B — 数据集与流程（UCI #447 液压基准）

- **数据集**：UCI Machine Learning Repository #447 `condition-monitoring-of-hydraulic-systems`；DOI `10.24432/C5CW21`；许可证 `CC BY 4.0`；文件包 SHA-256 `24128aad2ee45eea7e6b63ebbd9992cdf25d0483a2cebefbfc13bc69079af1f2`。引用：Helwig, N., Pignanelli, E., & Schütze, A. (2015).
- **循环**：**2205 total；1449 stable（主基准）；756 excluded**（官方 flag 表示静态条件可能未达到）。
- **矩阵/传感器**：扁平 zip 20 成员 = description/documentation/profile + **17 个传感器数据文件**；仅 **14 个物理传感器**用于主基准（PS1–PS6、EPS1、FS1–FS2、TS1–TS4、VS1）；**排除 CE / CP / SE**（派生目标代理/效率量）。
- **采样率/采样点**：PS/EPS = 100 Hz / 6000 采样点；FS = 10 Hz / 600 采样点；TS/VS = 1 Hz / 60 采样点。
- **特征**：14 传感器 × 4 统计量（mean / std ddof=0 / min / max）= **56 特征**。
- **目标**：profile 标签含 Cooler / Valve / Pump / Accumulator / stable；本轮 classifiers 只做 **Cooler + Valve**（Pump/Accumulator 仅作 grouping key 防泄漏）。
- **划分**：complete-profile group key 元组 `(cooler, valve, pump, accumulator)`，seed=447；train/val/test = **860 / 299 / 290 cycles = 86 / 29 / 29 groups**（60/20/20，组与循环都不跨集，非时间切分，属 group-held-out 插值）。
- **模型**：固定超参 sklearn pipeline（Logistic：Imputer(median)→StandardScaler→LogisticRegression(max_iter=2000, class_weight=balanced)；RandomForest：Imputer(median)→RandomForestClassifier(n_estimators=300, class_weight=balanced_subsample)），不调参不搜参。

---

## 13. Track B — 结果

**Cooler 模型表**（test；`docs/EVALUATION_REPORT_EXTERNAL_HYDRAULIC.md`）：

| family | val macro-F1 | test accuracy | test balanced acc | test macro-F1 | group-bootstrap 95% CI | test weighted-F1 |
|---|---|---|---|---|---|---|
| train-majority baseline | - | 0.2414 | 0.3333 | 0.1296 | [0.0625, 0.1951] | 0.0939 |
| logistic | 1.0 | 1.0 | 1.0 | 1.0 | [1.0, 1.0] | 1.0 |
| random_forest | 1.0 | 1.0 | 1.0 | 1.0 | [1.0, 1.0] | 1.0 |

**Valve 模型表**（test）：

| family | val macro-F1 | test accuracy | test balanced acc | test macro-F1 | group-bootstrap 95% CI | test weighted-F1 |
|---|---|---|---|---|---|---|
| train-majority baseline | - | 0.1034 | 0.25 | 0.0469 | [0.0, 0.0972] | 0.0194 |
| logistic | 0.5747 | 0.5897 | 0.6108 | 0.5692 | [0.4079, 0.6779] | 0.5816 |
| random_forest | 0.4256 | 0.4276 | 0.4664 | 0.4515 | [0.2511, 0.5915] | 0.4375 |

**Valve / logistic 每类 precision / recall / F1**（负结果保留）：

| class | code | precision | recall | f1 | support |
|---|---|---|---|---|---|
| close_to_total_failure | 73 | 0.4200 | 0.7000 | 0.5250 | 30 |
| severe_lag | 80 | 0.6071 | 0.3400 | 0.4359 | 100 |
| small_lag | 90 | 0.4091 | 0.5143 | 0.4557 | 70 |
| optimal_switching_behavior | 100 | 0.8333 | 0.8889 | 0.8602 | 90 |

**Cooler / logistic 每类（并列 1.0）**：close_to_total_failure(3) / reduced_efficiency(20) / full_efficiency(100) 均为 P=1.0 / R=1.0 / F1=1.0，support 100 / 120 / 70。

**精确混淆（logistic）**：**46 个 severe_lag(80) 被误判为 small_lag(90)**；**12 个 small_lag(90) 被误判为 severe_lag(80)**（另有 14 个 90 判为 100、8 个 90 判为 73 等，完整混淆矩阵见生成报告）。

**Caveats（边界说明）**：

- Cooler 1.0 是「当前表示/划分下任务可分」，不是更强的因果或现场诊断证据；无 repeated split、无 sensor ablation 支撑。
- 分数未校准（`model_score` 是未校准分类器输出，不能当概率读）。
- 单台架、stable-only、单次 group split、非时间切分（相邻 cycle 时间自相关可能跨 split）。
- 56 维统计特征丢弃了循环内时序结构。
- **不声称任何物理因果（no physical causality claim）**。

---

## 14. Diagnostic Evidence Integration（诊断证据集成）

链路：`DiagnosticEvidence → EvidenceItem → Hypothesis`，**只读、非因果**。

- `DiagnosticEvidence`（`src/contracts/evidence.py`）：`dataset_id` / `component` / `predicted_condition_code` / `predicted_condition_label` / 未校准 `model_score` / `global_top_feature_values` / `model_version` / `source_cycle` / `provenance`；`source_id()` = `diagnostic:{dataset_id}:{component}:{source_cycle}:{model_version}`。
- `to_evidence_item()` → `EvidenceItem(source_type=DIAGNOSTIC, citation==source_id, metadata.causal_status="non_causal_condition_classification")`。
- `integrate_diagnostic_evidence(state, diagnostics)`（`src/evaluation/diagnostic_integration.py`）fail-closed 规则：
  - 重复 `source_id` → raise ValueError（fail closed）。
  - **无诊断证据 → 显式 abstain**（无 Hypothesis、无 ProposedAction）。
  - **同一组件矛盾条件码 → 该组件 abstain**。
  - 一致证据 → 每组件一条非因果 `Hypothesis`（`cause` 只陈述条件分类结果，`confidence=LOW`，`pending_action=None`）。

**12 确定性契约场景 = 8 真实 + 2 缺失 + 2 合成矛盾**（ground truth 只用于选择记录，不进入 evidence provenance）。

**精确 7 项检查**：

| check | result |
|---|---:|
| evidence_attached | 12 |
| citation_valid | 12 |
| abstention_correct | 4 |
| contradiction_handled | 2 |
| unique_ids | 12 |
| hypothesis_evidence_id_presence_rate | 1.0 |
| semantic_unsupported_claim_rate | not_measured_no_entailment_annotations |

**未支持/未度量**：`semantic_unsupported_claim_rate` = **NOT MEASURED**（无独立 entailment 标注，不是 0）。这些是**契约检查**，不是诊断正确性、不是 RCA、不是工单推理、不是因果正确性。

---

## 15. 双轨为什么合理（Track A vs Track B）

| 维度 | Track A（合成，受控） | Track B（外部真实传感器） |
|---|---|---|
| 证明 | 端到端跑通 + 回归自检：资产解析、固定 plan、审批门态、trace、优雅降级 | 真实多传感器数据上的摄取/特征/条件分类/group-held-out/typed 证据契约 |
| 不能证明 | 真实世界 RCA 泛化（top-k 循环） | 端到端 RCA 准确率、工单推理、文档检索、工厂部署、因果 |
| 数据 | 25 资产 / 180 天 / 30 场景（同项目合成） | UCI #447：2205 / 1449 stable / 14 传感器（外部公开） |
| 关键结果 | top1/top3=1.0（circular）；evidence_recall=0.3698（synthetic regression coverage gap） | Cooler=1.0；Valve Macro-F1=0.5692（诚实负结果） |

一句话口径（原文保留）：

> The external hydraulic benchmark evaluates the real-sensor diagnostic evidence layer and its integration with the Agent evidence contract; it does not measure end-to-end root-cause-agent accuracy.

**Track B 不解决 Agent RCA 泛化**：它只为另一项条件分类任务增加非合成数据的诊断证据层；Track A 的 RCA top-k 同源循环仍然存在。两轨数据与 harness 独立，结果不能互相代替；evidence integration 有意复用共享 `AgentState` / `EvidenceItem` contracts。

---

## 16. 最终 Scope Freeze（范围冻结）

**已完成（completed）**

- Pydantic 契约层（asset / WO / meter / evidence / RAG / agent / evaluation）。
- 合成数据生成 + 入库（25 资产 / 180 天 / 6 失效模式）。
- SQLite `mode=ro` 数据层 + 参数化 SQL。
- 4 个 typed read-only tools + ToolRegistry（schema 声明）。
- 确定性 analytics（trend / anomaly / summary）。
- document retrieval / RAG scaffold（heading-aware 分块 + token-overlap 检索）。
- Agent：typed state + linear orchestration + 审批门 + trace。
- Track A：30 场景 + 7 项指标（另含场景总数）。
- Track B：UCI #447 摄取/特征/条件分类/held-out/typed 证据契约 + 12 契约场景。
- API（FastAPI）+ UI（Streamlit）。
- 测试：114 passed（49 → 66 → 71 → 114 演进）。

**五类冻结 Known Limitations（记录但不再修）**

1. **Agent policy / runtime**：fixed planner、no LLM、schema declared but not enforced；无 retry / timeout / checkpoint / resume / fallback。
2. **Evidence / retrieval**：文档检索不参与打分、claim grounding 弱、meter 证据重复 id；`evidence_recall=0.3698` 是 synthetic regression coverage gap（缺 events 工具 + WO 窗口/截断）。
3. **Evaluation validity**：Track A top-k circular；citation ID presence 不等于 semantic grounding；semantic unsupported claim rate 未测量。
4. **Safety / production**：审批 ephemeral，无认证 / 持久审计 / 终态 / 幂等；无结构化应用日志或 CI；Current Docker rebuild 未验证。
5. **External validity（Track B）**：单台架、stable-only、非时间切分、时间自相关、56 统计特征、无 repeated split / ablation、分数未校准、Valve Macro-F1 0.5692。

**未来工作（future work，只六主题，不承诺交付）**

1. 有界可选 LLM policy（constrained LLM policy）。
2. schema 强制（schema enforcement）。
3. BM25 / 更强检索（BM25 / stronger retrieval）。
4. claim 级 grounding / abstention（claim-level grounding）。
5. 运行时韧性（runtime resilience：retry / timeout / checkpoint / 合法迁移）。
6. 非循环端到端 RCA 评估（non-circular end-to-end RCA evaluation）。

**Docker 当前 caveat**：Historical base 镜像曾通过本地 API/UI health；Current Track B 依赖镜像因 daemon 不可用未重建，`docker compose config --quiet` 已通过，runtime rebuild / health **NOT VERIFIED**（历史 base 健康不是当前证明）。

---

## 17. 简历 Claim 红线（claim red lines）

**可以（can）**

- 「确定性 Agent Harness」「typed read-only tools」「人工审批门」「trace / 离线评估」。
- 双轨评估架构与诚实负结果（evidence_recall=0.3698、Valve Macro-F1=0.5692）。
- 114 个 pytest 用例、25 资产 / 180 天 / 30 场景。
- 例：Built a deterministic, testable industrial Agent harness wiring typed read-only tools, deterministic analytics, a document retrieval scaffold, and a human approval gate, with dual-track evaluation.

**谨慎（cautious — 必须带限定）**

- Track B 真实传感器结果：只能说「外部真实传感器上的条件分类与证据契约集成」，必须紧跟 caveat（单台架、stable-only、group-held-out、未校准）。
- 例：On a single controlled UCI hydraulic test rig, using 1,449 stable-only cycles and an uncalibrated profile-group-held-out condition classifier, the fixed baseline reached Cooler macro-F1 1.0 and Valve macro-F1 0.5692; this measures condition classification, not end-to-end RCA.

**绝不（never — 红线）**

- 不写 Top1/Top3 = 100%（循环指标）、不写 production、不写 LLM agent、不写 autonomous、不写 mature RAG、不写真实世界 RCA 准确率。
- 例：NEVER "achieved 100% root-cause accuracy"；NEVER "production industrial RCA agent"；NEVER "LLM-powered autonomous diagnostics"。

---

## 18. 中文简历最终推荐版本（3–4 条，诚实招聘价值）

> 定位：Agent 系统工程 + 确定性 Harness 先行。不含 Top1 100 / production / LLM / mature RAG 字样。

1. 设计并实现可测试的工业维护 Agent Harness：以 Pydantic 契约为模块边界，串联 typed read-only tools、确定性时间序列分析、文档检索 scaffold、JSON trace 与内存态人工审批流程，采用「确定性 Harness 先行、LLM policy 后置」架构。

2. 建立双轨评估：Track A 在 25 资产 / 180 天 / 30 个合成场景上定位 `evidence_recall=0.3698` 的 synthetic coverage gap；Track B 在单一受控 UCI #447 液压台架上，以 1449 个 stable-only cycles、14 个物理传感器和未校准的 profile-group-held-out classifier 验证条件分类，保留 Valve Macro-F1=0.5692 与 80↔90 混淆；不声明端到端 RCA。

3. 实现 read/write 权限边界：只读工具自动执行，写类意图仅产出 PENDING_APPROVAL 提案（v0 无外部写）；在 API、AgentRunner 与 TraceStore 三处校验 request_id 字符集/Windows 保留名，并执行 trace 路径包含检查以阻止文件名路径穿越。

4. 交付 114 个 pytest cases，分布于契约、数据、工具、分析、检索、Agent、API、UI 与双轨评估模块，作为确定性回归基线；不将用例数量表述为测试覆盖率。

**English resume version（与中文边界对齐）**

1. Built a testable industrial Agent harness with Pydantic contracts, typed read-only tools, deterministic time-series analytics, a document-retrieval scaffold, JSON traces, and an in-memory human-review workflow; kept LLM policy explicitly out of the current baseline.
2. Established two evaluation tracks: a 25-asset/180-day/30-scenario controlled synthetic regression track exposing evidence recall of 0.3698, and a single-rig UCI #447 stable-only, uncalibrated profile-group-held-out condition-classification track retaining Valve macro-F1 0.5692; not an end-to-end RCA claim.
3. Enforced the current read/write boundary with read-only SQLite (`mode=ro`), PENDING_APPROVAL proposals without external side effects, request-ID validation at API/runner/trace boundaries, and trace-path containment checks against filename traversal.
4. Added 114 pytest cases across contracts, data, tools, analytics, retrieval, Agent, API/UI, and both evaluation tracks as a deterministic regression suite; no coverage-percentage claim.

---

## 19. 自我介绍（可直接排练）

**30 秒**

我做一个工业维护根因分析的 Agent 项目，但它不是聊天机器人，而是一个可测试的确定性 Agent Harness：先用 typed 只读工具和确定性分析把管线跑通，LLM 留作后置 policy。当前可观测性是 JSON trace，审批只是内存态复核且没有外部写。双轨评估保留了 synthetic evidence_recall=0.3698 和 Valve 0.5692 这些负结果，说明我会看指标而不是美化数字。

**90 秒**

这个项目回答一个问题：怎么把一个概率模型放进可验证、可观测、可审批的工业软件系统。当前交付是确定性 baseline，无 LLM：契约先行（Pydantic 契约），只读工具查 SQLite，确定性趋势/异常分析，文档检索只是 token-overlap 的 scaffold 且不参与打分，写类动作走审批门，最后落 trace。评估分两轨：Track A 是 25 资产 / 180 天 / 30 场景的合成回归自检，我明确标注 top1/top3=1.0 是循环指标、evidence_recall=0.3698 是实际测得但仅属于 synthetic regression 的 coverage gap；Track B 用 UCI #447 真实液压传感器做条件分类，Cooler 1.0、Valve 0.5692，诚实保留 80↔90 混淆，并且明确它不证明端到端 RCA。这样既展示了系统化能力，又守住了口径边界。

**3 分钟**

先讲动机：工业 Agent 的价值不在 prompt 更聪明，而在 grounding、tool contract、permission、auditability、recovery、evaluation 这些外围确定性工程，所以我不先上 LangGraph 或 LLM，而是先做确定性 Harness。架构上分七层：契约叶子层、只读 SQLite 数据层、4 个 typed 工具、确定性分析、检索 scaffold、Agent 运行时（typed state + 线性编排 + 审批门 + trace）、API/UI。几个关键原则：LLM 不是 system of record、empty ≠ error、read 自由 write 提案、typed everywhere、证据带 source-id 但 grounding 弱。评估用双轨：Track A 合成数据做回归自检，Track B 外部真实传感器做条件分类与证据契约集成，两轨互不替代，结果不能互相代替。我重点讲诚实口径：哪些 1.0 是循环/静态/代理，evidence_recall 为什么只有 0.3698，以及下一阶段的六个方向（有界 LLM policy、schema 强制、BM25、claim 级 grounding、runtime 韧性、非循环端到端评估）。

---

## 20. 面试必会 20 问

1. **为什么保留 synthetic dataset？**
   - 30秒回答：合成数据提供可控失效模式 + 确定性 ground truth，能端到端回归验证工具选择/审批门态/trace/错误降级链路，真实传感器给不了这种受控边界。
   - 深挖方向：受控边界 vs 真实泛化的区别；ground truth 只用于评估、不入库不进镜像。

2. **为什么 synthetic 仍然有价值？**
   - 30秒回答：它验证系统行为正确性而非真实诊断泛化，可控、可复现、成本低，是「Harness 先行」的回归基座。
   - 深挖方向：可复现性如何支撑 CI 门禁；固定 seed 与幂等。

3. **为什么 synthetic Top-1 不能证明 generalization？**
   - 30秒回答：top-1=1.0 是 generator 与 synthesizer 同源关键词/信号造成的循环验证，只证明自洽。
   - 深挖方向：同源循环的具体机制；用 held-out 集破环的路径。

4. **为什么选择 Hydraulic Systems？**
   - 30秒回答：UCI #447 官方、公开、可复现（固定 URL + SHA-256 + CC BY 4.0），有官方条件码 ground truth，适合验证非合成数据的条件分类与证据链路。
   - 深挖方向：SHA-256 硬校验与幂等下载；可复现性的意义。

5. **为什么只选择 stable cycles？**
   - 30秒回答：官方 stable flag 表示静态条件可能未达到，只取 stable 保证标签有效，并把结论限定在稳定工况。
   - 深挖方向：756 排除数的来源；不覆盖启动/过渡态的影响。

6. **为什么按 complete profile 分组 split？**
   - 30秒回答：防止同一实验 profile 的循环跨 train/test 泄漏，按 (cooler,valve,pump,accumulator) 分组，组与循环都不跨集。
   - 深挖方向：泄漏机制；找不到合法划分即报错、不回退随机 cycle。

7. **为什么 Pump / Accumulator 参与 grouping 但暂不作为 target？**
   - 30秒回答：它们只作 grouping key 防泄漏，本轮不把其分类结果纳入声明，只聚焦 cooler/valve，避免声明过宽。
   - 深挖方向：什么条件下才扩展 target；保持相同 split/evidence 纪律。

8. **为什么排除 CE / CP / SE？**
   - 30秒回答：它们是派生/效率量（冷却效率/功率/效率因子），与 cooler 目标接近，可能成为 target proxy / 泄漏源，只用 14 个物理传感器。
   - 深挖方向：proxy 泄漏的风险；物理传感器 vs 派生量的边界。

9. **为什么先用 statistical features，不直接上 LSTM？**
   - 30秒回答：先建立可复现、可审计基线（14×4=56 特征），并把「丢弃循环内时序结构」记为已知限制，LSTM 是后续假设不在本轮。
   - 深挖方向：56 特征公式；时序结构丢失的代价；先基线后复杂模型的原则。

10. **为什么 Cooler 是 1.0？**
    - 30秒回答：在当前 stable-regime + 56 维统计表征 + profile-group-held-out 下 cooler 三类高度可分，这是「任务可分」而非因果/现场证据。
    - 深挖方向：无 repeated split / sensor ablation 支撑；bootstrap CI。

11. **为什么你不把 1.0 写成工业诊断准确率？**
    - 30秒回答：它是单一台架、稳定工况、单次 split 的离线分类分数，不是现场/工厂/跨设备诊断准确率。
    - 深挖方向：离线 benchmark vs 生产性能的差距。

12. **Valve 为什么难？**
    - 30秒回答：56 维统计表征下 severe_lag(80) 与 small_lag(90) 明显混淆，logistic 把 100 个 80 中的 46 个判为 90、70 个 90 中的 12 个判为 80，原因只作 hypothesis，未做 ablation 归因。
    - 深挖方向：特征压缩 / group shift / 模型容量 / 有序标签 / 时序信息丢失；不声称物理上天然不可分。

13. **为什么 Valve 0.5692 反而是有价值的结果？**
    - 30秒回答：这是诚实保留的负结果，证明同台架条件分类并非总容易，暴露 80↔90 混淆，说明必须保留 per-class F1 与混淆矩阵。
    - 深挖方向：不能只报平均分；负结果的价值。

14. **real diagnostic evidence 和 root cause 有什么区别？**
    - 30秒回答：diagnostic evidence 是「条件状态分类」（非因果）；root cause 是「为什么坏 + 该开什么工单」，Track B 只产出前者。
    - 深挖方向：条件分类 ≠ 根因诊断。

15. **Diagnostic model 是否能证明 causality？**
    - 30秒回答：不能，条件分类正确 ≠ 根因诊断正确，本项目不做任何因果证明。
    - 深挖方向：因果 vs 相关；为何不伪造因果声明。

16. **为什么不能给 Hydraulic dataset 伪造 Work Orders？**
    - 30秒回答：UCI 数据没有工单/维修文档/技师记录，伪造会污染证据边界并误导成「真实 RCA」。
    - 深挖方向：证据边界的完整性；Track B 不扩写成完整 Agent。

17. **什么情况下 Agent 应该 abstain？**
    - 30秒回答：fail-closed——无诊断证据 abstain（无假设无动作）；同一组件矛盾条件码 abstain（不产出假设）。
    - 深挖方向：abstention_correct=4 / contradiction_handled=2 的验证方式。

18. **Citation 存在为什么不等于 grounding 正确？**
    - 30秒回答：citation id 存在只验证「证据挂载 + id 引用」，不验证语义是否真正支撑结论；semantic unsupported claim rate 因无独立 entailment 标注而为 NOT MEASURED。
    - 深挖方向：evidence id presence vs semantic grounding；citation valid vs citation precision。

19. **当前 Project 01 最大的 Agent 层薄弱点是什么？**
    - 30秒回答：无 LLM tool loop（固定规则）、无 checkpoint/retry/timeout/recovery、检索文档不参与打分（装饰性 RAG）、claim grounding 弱、evidence_recall=0.3698、审批内存态无认证无审计。
    - 深挖方向：逐项对应 NEXT_PHASES 的 P0 修复路径。

20. **为什么下一步不是 Multi-Agent？**
    - 30秒回答：单 agent 的确定性基线尚未闭环 runtime、grounding 与 evaluation，multi-agent 只会放大协调/校验/可观测复杂度，属过早优化。
    - 深挖方向：先单 agent 可靠再谈多智能体；复杂度 vs 收益。

---

## 21. 代码学习地图（10–15 模块）

按「一次请求的真实数据流」学习，不要逐个背文件。P0=必学，P1=进阶，可忽略=参考。

| # | 路径 | 角色 | 学习深度 | 优先级 |
|---|---|---|---|---|
| 1 | `src/contracts/`（common / agent / evidence / assets / work_orders / meter / rag / evaluation） | 契约叶子层，跨模块边界 | 每个契约字段 + empty≠error 语义 | P0 |
| 2 | `src/db/schema.py` + `src/db/repository.py` | DDL + 只读 Repository（mode=ro、参数化 SQL） | 读查询怎么被封装成 typed 输出 | P0 |
| 3 | `src/tools/`（asset/meter/work_order）+ `src/agent/tools.py` | 工具层 + ToolRegistry + schema 声明 | 4 工具签名、ToolResult、schema 声明 vs 未强制 | P0 |
| 4 | `src/agent/runner.py` + `src/agent/planner.py` | 编排 + interpret/plan | 顺序调用、状态推进、固定 4-tool plan | P0 |
| 5 | `src/agent/executor.py` | 执行工具 + 转证据 | 逐调用 trace、`[:10]` 截断、EvidenceItem 转换 | P0 |
| 6 | `src/agent/synthesizer.py` | 规则打分 + 生成假设/提案 | `_rank()` 只消费 WO+meter，DOCUMENT 不参与 | P0 |
| 7 | `src/agent/policy.py` + `src/agent/request_id.py` | 审批门 + request_id 安全 | PENDING→APPROVED/REJECTED、PermissionError、id 校验/路径包含 | P1 |
| 8 | `src/agent/tracing.py` | TraceStore | TraceRecord 落盘/回读，无 replay | P1 |
| 9 | `src/analytics/`（trend / anomaly） | 确定性数值分析 | baseline vs recent、relative_change、MAD/zscore | P1 |
| 10 | `src/rag/`（chunking / retriever） | 分块 + keyword 检索 | heading-aware chunk + token-overlap，非 BM25/向量 | P1 |
| 11 | `src/evaluation/`（scenarios / metrics / runner） | Track A 离线评估 | 30 场景、7 指标、循环/静态/代理口径 | P0 |
| 12 | `src/benchmarks/hydraulic.py` | Track B 摄取/特征/分类/split | 下载校验、56 特征、group split、两模型 | P1 |
| 13 | `src/evaluation/diagnostic_integration.py` | 诊断证据集成 | DiagnosticEvidence→EvidenceItem→Hypothesis/abstain、12 场景 7 检查 | P1 |
| 14 | `src/api/main.py` + `ui/streamlit_app.py` | FastAPI + Streamlit | 端点、审批表内存态、UI 四页面 | P1 |
| 15 | `src/config.py` + `scripts/` | 配置 + 数据/评估入口脚本 | Settings/SecretStr、生成/入库/评估脚本 | 可忽略 |

---

## 22. 用户学习计划（无开发任务）

**2 小时（跑通 + 建立心智模型）**

- 读 `README.md`（定位/架构/口径警示）+ `docs/HANDBOOK.md` §1–§2（概览与现状/目标架构）。
- 跑通：生成数据 → 入库 → `pytest` → `run_evaluation.py` → 起 API 看 `/docs`。
- 亲手 `POST /agent/query`（"A001 stopped this week."）→ approve → 看 trace。
- 目标：能一句话说清「确定性 Harness 先行、LLM 后置」与「read 自由、write 审批」。

**半天（跟一次完整数据流 + 双轨评估）**

- 按 HANDBOOK §0 学习路线，从 `AgentRunner.run` 断点跟 interpret→plan→execute→synthesize。
- 读 `docs/EVALUATION_METHODOLOGY.md` + `docs/EVALUATION_REPORT.md`：逐项解释 7 指标为什么是循环/静态/代理，evidence_recall 为什么 0.3698。
- 读 `docs/benchmarks/HYDRAULIC_SYSTEMS_BENCHMARK.md` + `docs/EVALUATION_REPORT_EXTERNAL_HYDRAULIC.md`：能解释 Cooler 1.0 / Valve 0.5692 与 80↔90 混淆，以及「条件分类 ≠ RCA」。
- 目标：能复述双轨「证明/不能证明」对比表。

**额外时间（安全 + 边界 + 面试彩排）**

- 读 `docs/SAFETY_AND_THREAT_MODEL.md` + `docs/NEXT_PHASES.md`：能列生产写 blocker 与六个未来主题。
- 读 `docs/EXTERNAL_EVIDENCE_INTEGRATION.md`：12 场景 7 检查逐项口径。
- 排练本文件第 19/20/23 节，确保红线话术不越界。

---

## 23. 面试危险问题（safe truthful answers）

- **Q：Top1/Top3=100%，模型很准吧？**
  - 答：不是。这是循环指标——生成逻辑与分类逻辑同源，只证明自洽，不证明真实泛化；evidence_recall=0.3698 是实际测得的 synthetic regression coverage gap，不是现场指标。
- **Q：safety_gate_compliance=1.0 说明系统安全吗？**
  - 答：不能。它只查提案停在 PENDING 门态，是静态代理；v0 本就不做外部写，恒真。执行级安全需接真实写后重新证明。
- **Q：这是不是生产系统 / 上线了吗？**
  - 答：不是。无认证、无审计、无结构化日志、无 CI，审批是进程内内存态，Docker 当前镜像 rebuild 未验证。定位是可验证的确定性 baseline，不是生产。
- **Q：为什么没接 LLM 却叫 agent？**
  - 答：架构按 LLM 可插拔设计（planner/synthesizer 可替换，工具 schema 已备好）；先做确定性基线是为了让评估、安全、观测这些外围确定性系统先可靠。
- **Q：审批可信吗？**
  - 答：当前不可信——approved_by 硬编码、无认证、可逆、无终态、内存态跨进程不一致；这是接真实写前的 blocker。
- **Q：trace 能做审计吗？**
  - 答：不能。trace 记录调用/证据/假设/状态，但不含 approved_by/approved_at/审批结果，且无 replay；审计需单独落库。
- **Q：工具 schema 生效吗？**
  - 答：schema 已声明（`schemas()`），但注册表 `call()` 不按 schema 校验，边界靠工具内部 + days/limit 参数；这是已知 PARTIAL。
- **Q：怎么防 prompt injection？**
  - 答：当前把 retrieved 文档当 data、不执行指令，且无 LLM 故无指令跟随面；有场景覆盖。但这不是接 LLM 后的防御证明。
- **Q：Track B 证明了 RCA 吗？**
  - 答：没有。它只验证摄取/特征/条件分类/held-out/typed 证据契约，Cooler 1.0 / Valve 0.5692 是条件分类分数，不是根因诊断/工单/文档/部署/因果。
- **Q：Valve 0.5692 是不是说系统很烂？**
  - 答：不是「烂」，是诚实负结果。它证明同台架条件分类并非总容易，暴露 80↔90 混淆，说明必须看 per-class F1 与混淆矩阵，不能只报平均分。

---

## 24. 给 ChatGPT 的最终事实包（Final Fact Pack）

> 本段为机器可读风格的高度结构化事实清单；只给 ChatGPT 时，凭本节即可复述全部关键事实，不依赖上文。

### 项目身份

| 字段 | 值 |
|---|---|
| name | Industrial Maintenance / Root-Cause Agent（工业维护根因分析 Agent） |
| type | 作品集项目 / Portfolio；确定性 Agent Harness baseline（无 LLM） |
| dates | Historical hardening 2026-08-21；Track B report 2026-09-01；Portfolio v1.0 final freeze 2026-09-04 |
| status | FROZEN（最终交接，不改代码/文档/报告/配置/测试/git） |
| positioning | Evidence-oriented Industrial Agent Harness；Deterministic RCA Baseline；确定性 Harness 先行、LLM policy 后置 |
| explicitly-not | Production RCA Agent / LLM Agent / Autonomous Agent / mature RAG |

### 架构

- current：UI(Streamlit)/API(FastAPI) → AgentRunner(interpret→plan→execute→synthesize→policy→trace) → typed read tools(asset/WO/meter) + retrieval scaffold(chunking+keyword) → SQLite(mode=ro) + data/docs/*.md → deterministic analytics(trend/anomaly)。
- current has NO：LLM、LangGraph、graph、CLI、retry、timeout、checkpoint、resume、fallback、replay、conversation/summary/long-term memory；只有单次 `AgentState` working state。
- future (仅设计，NEXT_PHASES)：bounded runtime、LLM policy、schema-enforced gateway、BM25、structured claims+verifier、runtime store。

### 当前实现要点

- contracts（Pydantic，叶子层）：AgentState、ToolResult(ok/data/error/empty)、ToolError(code/message/retryable/context)、EvidenceItem、Hypothesis、ProposedAction(status=PENDING_APPROVAL)、ApprovalStatus(PENDING_APPROVAL/APPROVED/REJECTED)。empty≠error。
- tools：exactly 4 = get_asset / search_recent_work_orders / get_meter_history / search_docs。read-only、参数化 SQL、mode=ro。schema declared not enforced。无 LLM calling。
- RAG：heading-aware chunk + token-overlap keyword。NOT BM25/vector/hybrid/rerank。docs NOT in scoring（_rank 只消费 WO+meter）。
- grounding：traceability≠grounding；citation exists≠correct；weak；semantic unsupported NOT MEASURED。
- safety：read 自由 / write 提案；pending；v0 无外部写；静态 safety proxy；审批 ephemeral、无 auth/audit。
- runtime：state+linear，非 graph/recovery；无 retry/timeout/checkpoint/resume/fallback。

### Track A（合成）

- 25 assets / 180 days / 30 scenarios；7 指标 + total_scenarios=30。
- asset_resolution_accuracy=1.0（正则）；root_cause_top1=1.0（circular）；root_cause_top3=1.0（circular）；tool_selection_accuracy=1.0（static）；safety_gate_compliance=1.0（proposal-state）；recovery_rate=1.0（graceful-error/proxy）；evidence_recall=0.3698（synthetic regression coverage gap，非现场指标）。
- recall 成因：EV-* 无 events 工具不可达；WO days=30/limit=20；executor `[:10]` 截断。
- 无真实世界 RCA 准确率。

### Track B（外部）

- dataset：UCI #447，DOI 10.24432/C5CW21，CC BY 4.0，SHA-256 `24128aad2ee45eea7e6b63ebbd9992cdf25d0483a2cebefbfc13bc69079af1f2`。
- cycles：2205 total / 1449 stable / 756 excluded。17 矩阵 / 14 物理（排除 CE/CP/SE）。56 stats（14×4 mean/std ddof=0/min/max）。
- 采样率：PS/EPS 100Hz/6000；FS 10Hz/600；TS/VS 1Hz/60。
- 目标标签：Cooler/Valve/Pump/Accumulator/stable；classifiers Cooler+Valve。
- split：group key tuple (cooler,valve,pump,accumulator)，seed=447；860/86、299/29、290/29。
- Cooler：majority macro-F1 .1296；logistic 1.0；random_forest 1.0（caveat：任务可分，非因果/现场证据）。
- Valve：majority .0469；logistic .5692（acc .5897）；random_forest .4515（acc .4276）。
- Valve logistic per-class：close P.4200/R.7000/F.5250；severe P.6071/R.3400/F.4359；small P.4091/R.5143/F.4557；optimal P.8333/R.8889/F.8602。
- 混淆：46 severe(80)→small(90)；12 small(90)→severe(80)。无物理因果声明。
- evidence integration：12 = 8 real + 2 missing + 2 synthetic contradictions；evidence_attached=12、citation_valid=12、abstention_correct=4、contradiction_handled=2、unique_ids=12、presence_rate=1.0、semantic_unsupported=NOT MEASURED。

### Tests / 工程状态

- 当前 114 passed；chronology：49（historical）→ 66（historical）→ 71（pre-external）→ 114（current）。冻结验证环境：2026-09-04，Windows，Python 3.9.13，命令 `.\.venv\Scripts\python.exe -m pytest -q -p no:cacheprovider`。
- `pip check`：`No broken requirements found.`；`docker compose config --quiet` pass；Current Track B Docker runtime rebuild NOT VERIFIED（daemon 不可用；历史 base 健康 ≠ 当前证明）。

### 安全声明边界（safe claims）

- CAN：确定性 harness、typed 契约、只读工具、审批门、trace、双轨评估、诚实负结果、evidence_recall=0.3698、114 tests。
- CAUTIOUS：Track B 真实传感器条件分类（必须带 caveat）；Docker 历史 base 曾健康。
- AVOID / NEVER：Top1/Top3=100%、production、LLM agent、autonomous、mature RAG、真实世界 RCA 准确率、因果、校准概率。

### 五类冻结限制（known limits，记录不修）

1 Agent policy/runtime：fixed planner、no LLM、schema not enforced、no retry/timeout/checkpoint/resume/fallback。2 Evidence/retrieval：docs not scoring、weak grounding、duplicate meter evidence id、synthetic evidence_recall 0.3698。3 Evaluation validity：Track A circular、citation presence≠grounding、semantic unsupported NOT MEASURED。4 Safety/production：ephemeral approval、no auth/audit/CI/structured logs、current Docker rebuild unverified。5 Track B external validity：single rig、stable-only、non-chronological、temporal correlation、56 stats、no repeated split/ablation、uncalibrated、Valve .5692。

### 未来（six themes，仅方向，不承诺）

1 constrained LLM policy；2 schema enforcement；3 BM25/stronger retrieval；4 claim-level grounding；5 runtime resilience；6 non-circular end-to-end RCA evaluation。

### 推荐简历 bullet（中文，3–4 条）

1 可测试工业 Agent Harness：Pydantic contracts + typed read-only tools + deterministic analytics + retrieval scaffold + JSON trace + in-memory review workflow。2 双轨评估：Track A 25 assets/180 days/30 synthetic scenarios，定位 evidence_recall 0.3698；Track B 单一受控 UCI #447 台架、1449 stable-only cycles、未校准 group-held-out condition classifier，保留 Valve Macro-F1 0.5692，非端到端 RCA。3 read/write boundary：PENDING_APPROVAL proposal、无外部写；API/Runner/TraceStore request-id 校验与 trace 路径包含防护。4 114 pytest cases across core modules and both evaluation tracks；不声明覆盖率。

### Recommended English resume bullets

1 Testable deterministic industrial Agent harness with Pydantic contracts, typed read-only tools, analytics, a retrieval scaffold, JSON traces, and an in-memory review workflow. 2 Two-track evaluation: controlled synthetic regression (25 assets/180 days/30 scenarios; evidence recall 0.3698) plus a single-rig UCI #447 stable-only, uncalibrated group-held-out condition classifier (Valve macro-F1 0.5692), explicitly not end-to-end RCA. 3 Read-only SQLite and PENDING_APPROVAL proposals with no external writes, plus request-ID/path-containment guards. 4 114 pytest cases across contracts, data, tools, analytics, retrieval, Agent, API/UI, and evaluation; no coverage-percentage claim.

### 面试定位一句话

「我做一个可验证、可观测、可审批的确定性工业 Agent Harness，用双轨评估守口径：合成数据做回归自检，外部真实传感器做条件分类与证据契约，诚实保留 evidence_recall=0.3698 与 Valve 0.5692 的负结果，LLM 留作后置 policy。」
