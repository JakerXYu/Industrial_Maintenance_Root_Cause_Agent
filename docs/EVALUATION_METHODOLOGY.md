# 评估方法论 EVALUATION_METHODOLOGY

> 本文定义当前指标的精确定义（分子/分母 + 缺陷）、数据泄漏与循环性、未来评估设计、
> 新指标公式、切片、重复运行、延迟/成本、回归门禁与报告归属。配套：
> `docs/CAPABILITY_MATRIX.md`（能力状态）、`docs/EVALUATION_REPORT.md`（当前数字）、
> `docs/SAFETY_AND_THREAT_MODEL.md`（安全评估）、`docs/NEXT_PHASES.md`（落地计划）。

## 1. 当前指标（分子 / 分母 + 缺陷）

实现见 `src/evaluation/metrics.py`；当前值见 `docs/EVALUATION_REPORT.md`。

| 指标 | 分子 | 分母 | 当前值 | 缺陷（caveat） |
|---|---|---|---|---|
| asset_resolution_accuracy | 解析出的 asset_id == 期望 asset_id 的场景数 | 有 `expected_asset_id` 的场景数（28：25 个资产场景 + 3 个带期望资产的对抗场景） | 1.0 | 只测正则解析，不测消歧；ambiguous/missing 不计入分母 |
| root_cause_top1 | top-1 cause == 期望失效模式的场景数 | 有 `expected_root_cause` 的场景数（28：25 个资产场景 + 3 个带期望根因的对抗场景） | 1.0 | 与合成数据生成逻辑同源，属循环验证（见 §2） |
| root_cause_top3 | 期望失效模式 ∈ top-3 的场景数 | 同上 | 1.0 | 同上，循环 |
| evidence_recall | 各场景 `|相关证据 ∩ 召回证据| / |相关证据|` 的均值 | 有 `relevant_evidence_ids` 的场景数 | 0.3698 | gold 相关证据含 EV-* 事件 id，但无 events 工具故不可达；WO 查询 days=30/limit=20 且 executor 截断前 10 条，导致大量 gold WO id 未召回。检索 DOCUMENT 证据不增加 recall（recall 只取 gold 交集） |
| tool_selection_accuracy | 场景 `required_tools ⊆ tools_called` 的场景数 | 有 `required_tools` 的场景数 | 1.0 | 固定 plan 恒调用同样 4 工具，指标恒 1.0，无区分度（静态） |
| safety_gate_compliance | `proposed_action_status == PENDING_APPROVAL` 的提案数 | 有 proposed_action 的结果数 | 1.0 | 只检查“提案门态”，非执行级安全；v0 无外部写所以恒真（代理/静态） |
| recovery_rate | 边界场景到达期望终态（error/complete/pending）的场景数 | 非 normal 场景数（5） | 1.0 | 场景级终态断言，只证明优雅降级（不崩），不是重试/恢复（代理） |

共 **7 项指标** + `total_scenarios` 计数（`MetricsSnapshot` 共 8 个字段，其中 `total_scenarios=30` 是场景计数而非指标）。

## 2. 数据泄漏 / 循环性

- **同源循环**：`scripts/generate_synthetic_data.py` 用同一套失效模式（lubrication_degradation 等 6 种）
  及其关键词/信号扰动注入数据；`src/agent/synthesizer.py` 的 `MODE_KEYWORDS` + 信号阈值打分与之一一对应。
  因此 top-1/top-3 = 1.0 主要证明“生成逻辑与分类逻辑一致”，不是对真实世界的泛化证据。
- **标注泄漏风险**：`src/evaluation/scenarios.py` 直接从 `ground_truth_failures.csv` 读期望根因与
  `relevant_evidence_ids`；该文件运行时对 agent 不可见（不入库、不进镜像），但评估与生成共享同一份标注。
- **装饰性 RAG（独立的 grounding 缺陷）**：`search_docs` 的 DOCUMENT chunk 被检索进 `evidence_ids`，但
  `_rank` 不消费它（证据使用率为 0）。这**不改变 recall 数值**——recall 取 `|相关证据 ∩ 召回证据|` 与 gold 交集，
  gold 只含 WO/EV id，DOCUMENT chunk 永远不在交集中。它暴露的是“检索到了却没用于推理”的证据使用/grounding 缺陷。
- **低 recall 的真实成因**：gold `relevant_evidence_ids` 含 EV-* 事件 id（见 `ground_truth_failures.csv`），
  但系统没有 events 工具，事件证据永远无法被召回；同时 WO 只看近 30 天（days=30）、limit=20 且 executor
  只取前 10 条（`src/agent/executor.py` `[:10]`），大量 gold WO id 因窗口/截断未被召回。

结论：当前所有指标只能定位为 **合成数据上的回归自检**，不能对外宣称“模型能力/生产可用性”。

## 3. 未来 held-out 集

- 新增独立保留集：资产范围、失效组合、文档措辞、噪声模式均不在生成/调参集内出现。
- 保留集不入生成脚本、不参与 `MODE_KEYWORDS` 调参；以新 seed 生成一次后冻结。
- 评估脚本拆分：`build_scenarios()` 增加 `split ∈ {train, heldout}` 参数，heldout 的 ground truth
  只在评估期读取，且不与训练集重叠资产。
- 目标：用 heldout 的 top-k / evidence_recall / 新指标证明泛化，替代当前同源自检。

## 4. 确定性 vs 活体模型（live-model）profile

- **确定性 profile（当前）**：无 LLM，同输入同输出，可逐次复现；适合做回归与安全门禁基线。
- **活体模型 profile（接 LLM 后）**：引入 `LLM_MODEL` 后同一场景多次运行结果可能抖动；
  需新增非确定性 profile：重复 N 次取均值/方差，并记录模型、温度、token、成本与超时重试行为。
- 两种 profile 分开报表，不混用门禁阈值：确定性用硬阈值，活体用“均值 + 下限”并配方差。

## 5. 新指标公式（建议）

针对 §1 的循环/静态/代理缺陷，新增以下可区分指标（接 LLM 前后均适用）：

- **证据使用率 evidence_utilization** = 被假设 `supporting_evidence_ids` 实际引用且参与打分的证据数 / 召回证据总数。
  目标：单独度量装饰性 RAG（当前 DOCUMENT 证据贡献为 0），与 recall 正交（recall 不受 DOCUMENT 证据影响）。
- **证据精度 evidence_precision** = `|相关证据 ∩ 召回证据| / |召回证据|`（recall 的对称面，当前被忽略）。
- **根因证据覆盖 cause_coverage** = 期望根因在 top-1 假设的 `supporting_evidence_ids` 中至少命中 1 条相关证据的场景数 / 场景总数。
  用于暴露“答对但证据挂错”的弱 grounding。
- **工具必要集对齐 tool_delta** = 1 − `|实际工具集 Δ 期望工具集| / |期望工具集|`，替代二进制 `⊆` 判断，避免固定 plan 恒 1.0。
- **执行级安全（写前）**：替换 `safety_gate_compliance` 为“审批后执行是否产生且仅产生一次预期副作用 + 失败是否补偿/回滚”的观测指标（接真实写路径后启用，见 NEXT_PHASES 生产写 blocker）。
- **LLM 健壮性 llm_recovery** = 注入模型掉线/超时/非法 JSON 后优雅降级的比率（接 LLM 后，NEXT_PHASES P0-2）。

## 6. 切片（slices）

- 按 `category`：normal / missing_asset / ambiguous_asset / prompt_injection / duplicate_records / unauthorized_write 分别报。
- 按失效模式：6 种模式各自 top-1/top-3/recall，暴露类别不平衡。
- 按数据质量：缺失值、重复读数、误导工单、延迟完工四类瑕疵各自的 recall（关联 `generate_synthetic_data.py` 的注入点）。

## 7. 重复运行

- 确定性 profile：单次即可，但 CI 中固定 seed 复跑确认可复现。
- 活体 profile：每场景重复 `N≥5`，报告 `mean ± std`，并用相同 seed 的多次抽样隔离模型抖动与数据抖动。

## 8. 延迟 / 成本

- 延迟：`AgentRunner` 已记录 `total_latency_ms` 与每工具 `latency_ms`（`TraceRecord`/`ToolCallTrace`）；
  评估应汇总 P50/P95/P99。
- 成本：接 LLM 后记录每次请求的 token（prompt/completion）与模型单价，汇总总成本；确定性 profile 成本为 0。

## 9. 回归门禁（regression gates）

- CI 硬门：`pytest` 全绿；确定性 profile 的 `root_cause_top1`、`root_cause_top3`、
  `safety_gate_compliance`（仅作门态回归，不作能力声明）、`recovery_rate` 不劣化。
- 新增门：`evidence_recall` 与 `evidence_precision` 的 heldout 下限；`cause_coverage` 下限；
  活体 profile 的 `llm_recovery` 下限。
- 写前门：接真实 CMMS 后启用执行级安全指标替代 `safety_gate_compliance`（见 NEXT_PHASES 生产写 blocker）。

## 10. 报告生成归属

- 报告格式（Markdown 内容、指标表、场景表、caveat 文案）由 `src/evaluation/runner.py` 的 `_write_report` 生成；
  `scripts/run_evaluation.py` 是入口（构造 `Repository` 并调用 `run_evaluation`，把报告写到 `docs/EVALUATION_REPORT.md`）。
- 归属原则：指标计算逻辑属于 `src/evaluation/metrics.py`；报告格式属于 `src/evaluation/runner.py`；
  本文档 `EVALUATION_METHODOLOGY.md` 是唯一“指标定义 + 局限 + 门禁”的权威来源，代码与报告不得与本文冲突。
- 变更指标时必须同步更新本文与 `docs/EVALUATION_REPORT.md`，禁止只改代码不改文档。

## 交叉引用

- 能力状态对照：`docs/CAPABILITY_MATRIX.md`
- 当前数字：`docs/EVALUATION_REPORT.md`
- 安全评估方法论：`docs/SAFETY_AND_THREAT_MODEL.md`
- 落地计划（LLM / heldout / CI / 新工具）：`docs/NEXT_PHASES.md`
