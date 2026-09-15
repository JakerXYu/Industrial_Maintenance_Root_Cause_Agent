# 评估方法论 EVALUATION_METHODOLOGY

> 本文定义当前指标的精确定义（分子/分母 + 缺陷）、数据泄漏与循环性、未来评估设计、
> 新指标公式、切片、重复运行、延迟/成本、回归门禁与报告归属。
> 评估正式分为两条**互不替代**的顶层轨，任何结果都必须先声明属于哪一轨：
> **Track A — Controlled Synthetic Agent Evaluation（受控合成智能体评估）** 与
> **Track B — External Real-Sensor Diagnostic Evaluation（外部真实传感器诊断评估）**。
> 配套：`docs/CAPABILITY_MATRIX.md`（能力状态）、`docs/EVALUATION_REPORT.md`（Track A 数字）、
> `docs/EVALUATION_REPORT_EXTERNAL_HYDRAULIC.md`（Track B 数字）、
> `docs/EXTERNAL_EVIDENCE_INTEGRATION.md`（Track B 证据集成链路）、
> `docs/benchmarks/HYDRAULIC_SYSTEMS_BENCHMARK.md`（Track B 权威边界）、
> `docs/SAFETY_AND_THREAT_MODEL.md`（安全评估）、`docs/NEXT_PHASES.md`（落地计划）。

两轨无数据重叠；Track B classifier harness 独立，evidence boundary 刻意复用共享 contracts。
指标与口径**不可互相替代**：Track A 的 1.0 是循环/静态/代理；Track B 的 cooler 1.0 是
同一台架、stable-only、单次 profile-group split 下的条件分类分数，不代表 RCA 或跨设备泛化。

## Track A — Controlled Synthetic Agent Evaluation（受控合成智能体评估）

### Purpose（目的）

验证「确定性基线端到端跑通 + 回归自检」：25 资产、180 天、30 场景，保留当前全部指标、工作流、
安全与边界场景。它回答的是——规则基线（固定 plan、无 LLM、只读工具、SQLite）能否在受控合成数据上
可复现地产出资产解析、根因 top-k、工具选择、证据召回、安全门态与优雅降级。它**不**回答真实世界泛化。

### What it tests（测试什么）

- **资产解析**：正则 `\bA\d{3}\b` 解析 asset_id 是否命中期望资产（不测消歧）。
- **根因 top-k**：规则分类器（`MODE_KEYWORDS` + 信号阈值）给出的 top-1 / top-3 是否命中期望失效模式。
- **证据召回**：gold `relevant_evidence_ids` 与召回证据的交集覆盖。
- **工具选择**：固定 plan 调用的工具集是否 ⊇ `required_tools`。
- **安全门态**：提案是否停留在 `PENDING_APPROVAL`。
- **恢复**：边界/对抗场景是否到达期望终态（error/complete/pending）。
- **30 场景**：normal / missing_asset / ambiguous_asset / prompt_injection / duplicate_records /
  unauthorized_write 等（实现见 `src/evaluation/scenarios.py`）。

### Metrics / Results（指标与结果）

实现见 `src/evaluation/metrics.py`；当前值见 `docs/EVALUATION_REPORT.md`。

| 指标 | 分子 | 分母 | 当前值 | 缺陷（caveat） |
|---|---|---|---|---|
| asset_resolution_accuracy | 解析出的 asset_id == 期望 asset_id 的场景数 | 有 `expected_asset_id` 的场景数（28：25 个资产场景 + 3 个带期望资产的对抗场景） | 1.0 | 只测正则解析，不测消歧；ambiguous/missing 不计入分母 |
| root_cause_top1 | top-1 cause == 期望失效模式的场景数 | 有 `expected_root_cause` 的场景数（28：25 个资产场景 + 3 个带期望根因的对抗场景） | 1.0 | 与合成数据生成逻辑同源，属循环验证（见下「局限」） |
| root_cause_top3 | 期望失效模式 ∈ top-3 的场景数 | 同上 | 1.0 | 同上，循环 |
| evidence_recall | 各场景 `|相关证据 ∩ 召回证据| / |相关证据|` 的均值 | 有 `relevant_evidence_ids` 的场景数 | 0.3698 | gold 相关证据含 EV-* 事件 id，但无 events 工具故不可达；WO 查询 days=30/limit=20 且 executor 截断前 10 条，导致大量 gold WO id 未召回。检索 DOCUMENT 证据不增加 recall（recall 只取 gold 交集） |
| tool_selection_accuracy | 场景 `required_tools ⊆ tools_called` 的场景数 | 有 `required_tools` 的场景数 | 1.0 | 固定 plan 恒调用同样 4 工具，指标恒 1.0，无区分度（静态） |
| safety_gate_compliance | `proposed_action_status == PENDING_APPROVAL` 的提案数 | 有 proposed_action 的结果数 | 1.0 | 只检查“提案门态”，非执行级安全；v0 无外部写所以恒真（代理/静态） |
| recovery_rate | 边界场景到达期望终态（error/complete/pending）的场景数 | 非 normal 场景数（5） | 1.0 | 场景级终态断言，只证明优雅降级（不崩），不是重试/恢复（代理） |

共 **7 项指标** + `total_scenarios` 计数（`MetricsSnapshot` 共 8 个字段，其中 `total_scenarios=30` 是场景计数而非指标）。

### Limitations（局限）

- **高合成 Top1/Top3 不是真实世界泛化**：`root_cause_top1` / `root_cause_top3` = 1.0 只说明
  「生成逻辑与分类逻辑一致」，**不是**对真实数据、真实设备或生产的泛化证据，不能对外宣称模型能力。
- **同源循环**：`scripts/generate_synthetic_data.py` 用同一套失效模式（lubrication_degradation 等 6 种）
  及其关键词/信号扰动注入数据；`src/agent/synthesizer.py` 的 `MODE_KEYWORDS` + 信号阈值打分与之一一对应。
- **标注泄漏风险**：`src/evaluation/scenarios.py` 直接从 `ground_truth_failures.csv` 读期望根因与
  `relevant_evidence_ids`；该文件运行时对 agent 不可见（不入库、不进镜像），但评估与生成共享同一份标注。
- **固定 planner（静态指标）**：plan 是确定性的 4 步（get_asset / search_recent_work_orders /
  get_meter_history / search_docs），`tool_selection_accuracy` 恒 1.0，无区分度。
- **弱 grounding**：`Hypothesis.supporting_evidence_ids` 无差别挂全部证据（未逐 claim 对齐），
  且 meter 用单一 `meter_summary:{asset_id}` 造成重复证据 id——存在「答对但证据挂错」的弱 grounding 缺陷。
- **装饰性 RAG（独立的 grounding 缺陷）**：`search_docs` 的 DOCUMENT chunk 被检索进 `evidence_ids`，但
  `_rank` 不消费它（证据使用率为 0）。这**不改变 recall 数值**——recall 取 `|相关证据 ∩ 召回证据|` 与 gold 交集，
  gold 只含 WO/EV id，DOCUMENT chunk 永远不在交集中。它暴露的是「检索到了却没用于推理」的证据使用/grounding 缺陷。
- **低 recall 的真实成因**：gold `relevant_evidence_ids` 含 EV-* 事件 id（见 `ground_truth_failures.csv`），
  但系统没有 events 工具，事件证据永远无法被召回；同时 WO 只看近 30 天（days=30）、limit=20 且 executor
  只取前 10 条（`src/agent/executor.py` `[:10]`），大量 gold WO id 因窗口/截断未被召回。

结论：**Track A 的所有指标**只能定位为 **合成数据上的回归自检**，不能对外宣称「模型能力/生产可用性」。
Track B 的 held-out 分数是真实数据上的条件分类结果，但仍不构成 RCA / 因果 / 生产可用性声明（见 Track B 节）。

### 未来 held-out 集

- 新增独立保留集：资产范围、失效组合、文档措辞、噪声模式均不在生成/调参集内出现。
- 保留集不入生成脚本、不参与 `MODE_KEYWORDS` 调参；以新 seed 生成一次后冻结。
- 评估脚本拆分：`build_scenarios()` 增加 `split ∈ {train, heldout}` 参数，heldout 的 ground truth
  只在评估期读取，且不与训练集重叠资产。
- 目标：用 heldout 的 top-k / evidence_recall / 新指标证明泛化，替代当前同源自检。

### 确定性 vs 活体模型（live-model）profile

- **确定性 profile（当前）**：无 LLM，同输入同输出，可逐次复现；适合做回归与安全门禁基线。
- **活体模型 profile（接 LLM 后）**：引入 `LLM_MODEL` 后同一场景多次运行结果可能抖动；
  需新增非确定性 profile：重复 N 次取均值/方差，并记录模型、温度、token、成本与超时重试行为。
- 两种 profile 分开报表，不混用门禁阈值：确定性用硬阈值，活体用「均值 + 下限」并配方差。

### 新指标公式（建议）

针对上述循环/静态/代理缺陷，新增以下可区分指标（接 LLM 前后均适用）：

- **证据使用率 evidence_utilization** = 被假设 `supporting_evidence_ids` 实际引用且参与打分的证据数 / 召回证据总数。
  目标：单独度量装饰性 RAG（当前 DOCUMENT 证据贡献为 0），与 recall 正交（recall 不受 DOCUMENT 证据影响）。
- **证据精度 evidence_precision** = `|相关证据 ∩ 召回证据| / |召回证据|`（recall 的对称面，当前被忽略）。
- **根因证据覆盖 cause_coverage** = 期望根因在 top-1 假设的 `supporting_evidence_ids` 中至少命中 1 条相关证据的场景数 / 场景总数。
  用于暴露「答对但证据挂错」的弱 grounding。
- **工具必要集对齐 tool_delta** = 1 − `|实际工具集 Δ 期望工具集| / |期望工具集|`，替代二进制 `⊆` 判断，避免固定 plan 恒 1.0。
- **执行级安全（写前）**：替换 `safety_gate_compliance` 为「审批后执行是否产生且仅产生一次预期副作用 + 失败是否补偿/回滚」的观测指标（接真实写路径后启用，见 NEXT_PHASES 生产写 blocker）。
- **LLM 健壮性 llm_recovery** = 注入模型掉线/超时/非法 JSON 后优雅降级的比率（接 LLM 后，NEXT_PHASES P0-2）。

### 切片（slices）

- 按 `category`：normal / missing_asset / ambiguous_asset / prompt_injection / duplicate_records / unauthorized_write 分别报。
- 按失效模式：6 种模式各自 top-1/top-3/recall，暴露类别不平衡。
- 按数据质量：缺失值、重复读数、误导工单、延迟完工四类瑕疵各自的 recall（关联 `generate_synthetic_data.py` 的注入点）。

### 重复运行

- 确定性 profile：单次即可，但 CI 中固定 seed 复跑确认可复现。
- 活体 profile：每场景重复 `N≥5`，报告 `mean ± std`，并用相同 seed 的多次抽样隔离模型抖动与数据抖动。

### 延迟 / 成本

- 延迟：`AgentRunner` 已记录 `total_latency_ms` 与每工具 `latency_ms`（`TraceRecord`/`ToolCallTrace`）；
  评估应汇总 P50/P95/P99。
- 成本：接 LLM 后记录每次请求的 token（prompt/completion）与模型单价，汇总总成本；确定性 profile 成本为 0。

### 回归门禁（regression gates）

- CI 硬门：`pytest` 全绿；确定性 profile 的 `root_cause_top1`、`root_cause_top3`、
  `safety_gate_compliance`（仅作门态回归，不作能力声明）、`recovery_rate` 不劣化。
- 新增门：`evidence_recall` 与 `evidence_precision` 的 heldout 下限；`cause_coverage` 下限；
  活体 profile 的 `llm_recovery` 下限。
- 写前门：接真实 CMMS 后启用执行级安全指标替代 `safety_gate_compliance`（见 NEXT_PHASES 生产写 blocker）。

### Report ownership（报告归属）

- 报告格式（Markdown 内容、指标表、场景表、caveat 文案）由 `src/evaluation/runner.py` 的 `_write_report` 生成；
  `scripts/run_evaluation.py` 是入口（构造 `Repository` 并调用 `run_evaluation`，把报告写到 `docs/EVALUATION_REPORT.md`）。
- 归属原则：指标计算逻辑属于 `src/evaluation/metrics.py`；报告格式属于 `src/evaluation/runner.py`；
  本文档 `EVALUATION_METHODOLOGY.md` 是唯一「指标定义 + 局限 + 门禁」的权威来源，代码与报告不得与本文冲突。
- 变更指标时必须同步更新本文与 `docs/EVALUATION_REPORT.md`，禁止只改代码不改文档。

## Track B — External Real-Sensor Diagnostic Evaluation（外部真实传感器诊断评估）

### Purpose（目的）

在**外部真实传感器数据**（UCI 液压系统状态监测数据集 #447）上，独立验证「数据摄取 → 特征提取 →
条件分类 → 同一台架 stable regime 的 profile-group-held-out 条件分类 → typed 诊断证据契约」链路，
并验证 `DiagnosticEvidence → EvidenceItem → AgentState → Hypothesis/Abstention` 的集成行为。
它**不是**完整 RCA、不生成工单、不检索文档、不声称工厂部署或因果证明。

### What it tests（测试什么）

- **摄取**：URL 下载 → SHA-256 硬校验（不匹配即失败）→ zip-slip 安全解压 → 成员数校验 →
  必需文件校验，且幂等（已存在则跳过）。
- **特征提取**：14 个物理传感器 × 4 个统计量（mean/std/min/max，`std` 为 `ddof=0`）= 56 个特征。
- **条件分类**：`cooler`（3 类）与 `valve`（4 类）两个目标，各跑 Logistic 与随机森林两个固定超参家族。
- **划分正确性**：complete-profile group 划分，组与循环都不跨集，每集都覆盖全部类别；不做随机 cycle 级回退。
- **group-held-out 评估**：模型只在训练集 fit；验证集只用于选型；测试集只报告一次。
- **证据契约**：诊断预测转为 `EvidenceSourceType.DIAGNOSTIC` 的 `EvidenceItem`，稳定 `source_id`、
  `citation`、非因果 `metadata`，缺失/矛盾输入触发 fail-closed 行为（见 `docs/EXTERNAL_EVIDENCE_INTEGRATION.md`）。

### Metrics / Results（指标与结果）

数据集（`docs/EVALUATION_REPORT_EXTERNAL_HYDRAULIC.md` 为原始数字来源，权威边界见
`docs/benchmarks/HYDRAULIC_SYSTEMS_BENCHMARK.md`）：

- **数据集**：`condition-monitoring-of-hydraulic-systems`（UCI #447），SHA-256
  `24128aad2ee45eea7e6b63ebbd9992cdf25d0483a2cebefbfc13bc69079af1f2`，CC BY 4.0。
- **循环**：2205 总循环；**1449 稳定（stable code 0）用于主基准**，756 非稳定循环被排除（stable-only）。
- **传感器**：14 个物理传感器（`PS1`–`PS6`、`EPS1`、`FS1`–`FS2`、`TS1`–`TS4`、`VS1`）；
  `CE`/`CP`/`SE` 是派生目标代理控制，**被排除**。
- **划分**：complete-profile group `(cooler, valve, pump, accumulator)` 共 144 组，按组 60/20/20，
  `seed=447`，train/val/test = 860/299/290 循环 = 86/29/29 组。**非时间切分**，属 group-held-out 插值，
  相邻 cycle 时间自相关可能仍跨 split，故报告按 group 重采样的 macro-F1 95% bootstrap 区间。
- **`cooler`**：两个固定配置的 test accuracy / macro-F1 均为 **1.0**（验证集并列）。这是当前表示/划分下的
  可分性，不是更强因果或现场诊断证据，也没有 repeated split / sensor ablation 支撑。
- **`valve`**（preferred = logistic，按验证集 macro-F1 选出）：

  | family | test accuracy | test macro-F1 |
  |---|---|---|
  | logistic | **0.5897** | **0.5692**（该 split 的 preferred） |
  | random_forest | 0.4276 | 0.4515 |

- **`valve` / logistic 每类 F1**（负结果保留）：`73`=0.5250、`80`=0.4359、`90`=0.4557、`100`=0.8602。
  `severe_lag(80)` 与 `small_lag(90)` 明显混淆（logistic 把 100 个 `80` 中的 46 个判为 `90`）。
- **证据集成（12 确定性契约场景）**：8 真实 profile-group-held-out test 预测 + 2 缺失证据 abstain +
  2 合成矛盾（详见 `docs/EXTERNAL_EVIDENCE_INTEGRATION.md`）。

  | check | result |
  |---|---:|
  | evidence_attached | 12 |
  | citation_valid | 12 |
  | abstention_correct | 4 |
  | contradiction_handled | 2 |
  | unique_ids | 12 |
  | hypothesis_evidence_id_presence_rate | 1.0 |
  | semantic_unsupported_claim_rate | not_measured_no_entailment_annotations |

### Limitations（局限）

- **不验证端到端 RCA**：条件分类正确 ≠ 根因诊断正确。Track B 只覆盖「真实传感器诊断证据层」及其与
  Agent 证据契约的集成，**不**覆盖 Track A 的 planner / synthesizer / 审批门 / 工单 / 文档检索 / 场景评估，
  也**不**度量端到端根因智能体的准确率。
- 权威英文表述（原文保留）：

  > The external hydraulic benchmark evaluates the real-sensor diagnostic evidence layer and its integration with the Agent evidence contract; it does not measure end-to-end root-cause-agent accuracy.

  中文解释：Hydraulic Systems 外部 Benchmark 验证的是真实传感器条件下的诊断证据层及其与 Agent Evidence Contract 的集成，而不是完整端到端 Root-Cause Agent 的准确率。
- **不证明生产可用 / 因果**：离线公开数据集结果，不构成现场/工厂部署能力；本项目不做因果证明。
- **分数未校准**：`model_score` 是未校准分类器输出，不能当概率读。
- **单数据集 / stable-only**：只在一个液压测试台的稳定工况上验证，排除 756 个未达静态条件的循环，
  不覆盖启动/切换/过渡状态，泛化边界有限。
- **证据检查是契约级**：`evidence_*` 检查验证的是 typed 证据挂载、citation id 存在、abstain/矛盾处理的
  契约行为，**不是**诊断正确性。
- **与 Track A 互不替代**：Track B 数据与 classifier harness 独立；Track A 保留 25 资产、180 天、30 场景、
  当前指标、工作流、安全与边界场景。

### Report ownership（报告归属）

- `docs/EVALUATION_REPORT_EXTERNAL_HYDRAULIC.md` 由 `scripts/run_hydraulic_benchmark.py` 生成
  （核心在 `src/benchmarks/hydraulic.py`，证据集成段由 `src/evaluation/diagnostic_integration.py` 追加）；
  它是 Track B 的原始数字来源，权威边界在 `docs/benchmarks/HYDRAULIC_SYSTEMS_BENCHMARK.md`，
  不属于 Track A 指标体系。
- 证据集成链路的契约语义与逐项检查见 `docs/EXTERNAL_EVIDENCE_INTEGRATION.md`（本文档与
  `diagnostic_integration.py` 及生成报告三者口径保持一致）。

## 交叉引用

- 能力状态对照：`docs/CAPABILITY_MATRIX.md`
- 当前数字（Track A）：`docs/EVALUATION_REPORT.md`
- 外部基准数字（Track B）：`docs/EVALUATION_REPORT_EXTERNAL_HYDRAULIC.md`
- 外部基准权威边界（Track B）：`docs/benchmarks/HYDRAULIC_SYSTEMS_BENCHMARK.md`
- 外部证据集成链路（Track B）：`docs/EXTERNAL_EVIDENCE_INTEGRATION.md`
- 安全评估方法论：`docs/SAFETY_AND_THREAT_MODEL.md`
- 落地计划（LLM / heldout / CI / 新工具）：`docs/NEXT_PHASES.md`
