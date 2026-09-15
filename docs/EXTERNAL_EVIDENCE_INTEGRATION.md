# 外部证据集成链路 EXTERNAL_EVIDENCE_INTEGRATION

> 本文（中文优先）说明 Track B 外部真实传感器诊断证据如何进入 Agent 证据契约，并精确界定
> 12 个确定性契约场景与 7 项检查各自**证明了什么、没证明什么**。
> 权威边界见 `docs/benchmarks/HYDRAULIC_SYSTEMS_BENCHMARK.md`；原始数字见
> `docs/EVALUATION_REPORT_EXTERNAL_HYDRAULIC.md`；实现见 `src/contracts/evidence.py` 与
> `src/evaluation/diagnostic_integration.py`。

## 一、链路：Diagnostic Service → Diagnostic Evidence → Agent Evidence Contract → Hypothesis / Abstention

证据集成是一条**只读、非因果**的契约链路，四个环节严格分开：

### 1. Diagnostic Service（诊断服务）

`src/benchmarks/hydraulic.py` 在 held-out test 上跑固定超参 sklearn pipeline（Logistic / 随机森林，
按验证集 macro-F1 选 preferred family），对每个 test cycle 产出一条硬分类预测。预测结果落到
`artifacts/benchmarks/hydraulic/test_predictions.csv`（忽略，不入库）。这一层只做条件分类，不做 RCA。

### 2. Diagnostic Evidence（诊断证据）

每条预测被建模为 `src/contracts/evidence.py` 的 `DiagnosticEvidence`（Pydantic 契约），字段：
`dataset_id`、`component`、`predicted_condition_code`、`predicted_condition_label`、
未校准 `model_score`、`global_top_feature_values`、`model_version`、`source_cycle`、`provenance`。
`source_id()` 稳定唯一：`diagnostic:{dataset_id}:{component}:{source_cycle}:{model_version}`。

关键语义：`model_score` 是**未校准**分类器输出，**不**映射成序数 Agent confidence；
`global_top_feature_values` 是全局重要特征在该 cycle 的原始取值，**不是**局部归因解释。

### 3. Agent Evidence Contract（Agent 证据契约）

`DiagnosticEvidence.to_evidence_item()` 转成 `EvidenceItem`：`source_type=DIAGNOSTIC`、
`source_id` 稳定、`citation == source_id`、`metadata.causal_status = "non_causal_condition_classification"`。
转换不产生任何根因主张或动作提案。

### 4. Hypothesis / Abstention（假设 / 弃权）

`src/evaluation/diagnostic_integration.py` 的 `integrate_diagnostic_evidence(state, diagnostics)`
把证据挂进 `AgentState`，fail-closed 规则如下：

- 按唯一 `source_id` 追加一条 `EvidenceItem`；重复 `source_id` 直接 `raise ValueError`（fail closed）。
- **无诊断证据** → 状态置 `COMPLETE`，显式 abstain：无 `Hypothesis`、无 `ProposedAction`。
- **同一组件出现矛盾条件码**（不同 model_version 预测不同 code）→ 该组件 abstain，不产出假设。
- **一致证据** → 每个组件产出一条 `Hypothesis`：`cause` 只陈述「条件分类结果」而非根因，
  `confidence=LOW`（未校准分数不升档），`supporting_evidence_ids` 只挂该组件自己的证据 id，
  `pending_action=None`。

## 二、12 个确定性契约场景

`build_diagnostic_scenarios` 固定产出 12 个场景，分类清晰、互不混同：

| 类别 | 数量 | 场景名 | 内容 |
|---|---|---|---|
| 真实 held-out 预测 | 8 | `normal_1`..`normal_8` | 8 个 seeded profile-group-held-out test 预测（按 cycle hash + 类别覆盖选择，**不依赖预测正确性或分数**） |
| 缺失证据 | 2 | `missing_1`、`missing_2` | 空输入（无任何诊断证据），验证 fail-closed abstain |
| 合成矛盾 | 2 | `contradiction_1`、`contradiction_2` | 每对共享同一组件但携带不同预测条件码的合成证据（`-edge-*-a` / `-edge-*-b` 两个 model_version） |

- **8 个真实预测**：每个真实类别取一个 + 额外 seeded 周期，共 8 条。其中包含一个自然的
  valve `80→90` 误分类（cycle 265：真实 `severe_lag(80)` 被预测为 `small_lag(90)`），如实保留、不做美化。
- **ground truth 只用于选择记录**（保证类别覆盖），**不进入 Agent 证据 provenance**。
- **2 个缺失 + 2 个合成矛盾**与 8 个真实预测在报告中**分列计数**，不混为「12 个真实诊断」。

## 三、7 项检查（exact checks）

`evaluate_diagnostic_integration` 返回的精确检查结果（`evidence_integration.json`，忽略不入库）：

| check | result |
|---|---:|
| evidence_attached | 12 |
| citation_valid | 12 |
| abstention_correct | 4 |
| contradiction_handled | 2 |
| unique_ids | 12 |
| hypothesis_evidence_id_presence_rate | 1.0 |
| semantic_unsupported_claim_rate | not_measured_no_entailment_annotations |

各项检查口径：

- `evidence_attached`：12 个场景中累计挂载的 `EvidenceItem` 数（8 真实 + 4 合成矛盾证据 = 12；2 缺失场景不挂载）。
- `citation_valid`：`source_type == DIAGNOSTIC` 且 `citation == source_id` 且 `source_id` 非空 的证据数。
- `abstention_correct`：缺失（2）与矛盾（2）场景均「无假设 + `COMPLETE` + final_answer 显式 abstain」的个数 = 4。
- `contradiction_handled`：矛盾场景正确 abstain 的个数 = 2。
- `unique_ids`：全部挂载证据 `source_id` 去重后的个数 = 12。
- `hypothesis_evidence_id_presence_rate`：产出的假设中 `supporting_evidence_ids` 非空的比例 = 1.0。
- `semantic_unsupported_claim_rate`：显式记为 `not_measured_no_entailment_annotations`（未度量）。

## 四、三项关键区别（这些检查没有证明什么）

### 1. evidence ID presence ≠ semantic grounding（证据 id 存在 ≠ 语义 grounding）

`hypothesis_evidence_id_presence_rate = 1.0` 只表示「每一条被产出的假设都挂了至少一个证据 id」。
它**不**证明该证据在语义上支持（entail）该假设的 claim；不存在 claim 级对齐或蕴含标注，因此
「证据确实支撑结论」这件事**未被度量**。这是 id 存在性检查，不是语义 grounding 检查。

### 2. citation valid ≠ citation precision（引文合法 ≠ 引文精度）

`citation_valid = 12` 只验证 `citation` 字符串等于一个稳定 `source_id`（格式正确、可溯源）。
它**不**度量被引证据是否是「对该 claim 而言正确/相关」的证据——`citation_precision`
（引文精度）在 Track B **未计算**（对应 `CAPABILITY_MATRIX` 中 Citation Precision = MISSING）。

### 3. semantic unsupported claim rate NOT MEASURED（语义无依据主张率未度量）

本项目没有独立的 entailment 标注，无法判断一条假设里是否存在「无证据支撑的主张」，因此
`semantic_unsupported_claim_rate` 明确为 `not_measured_no_entailment_annotations`，**不是 0**，
也不是「已通过」。它不代表没有无依据主张，只代表这项度量在当前证据链路上不可计算。

## 五、边界重申

- 以上全部是**契约检查**（typed 证据挂载、citation id 存在、abstain 正确、矛盾处理、唯一 id），
  **不是**诊断正确性，也不是 RCA / 工单推理 / 因果正确性。
- 外部液压基准评估的是「真实传感器诊断证据层」及其与 Agent 证据契约的集成；它**不**度量端到端
  根因智能体准确率（见 `docs/EVALUATION_METHODOLOGY.md` Track B 节）。
- 交叉引用：`docs/benchmarks/HYDRAULIC_SYSTEMS_BENCHMARK.md`（权威边界）、
  `docs/EVALUATION_REPORT_EXTERNAL_HYDRAULIC.md`（原始数字）、`docs/EVALUATION_METHODOLOGY.md`（方法论）。
