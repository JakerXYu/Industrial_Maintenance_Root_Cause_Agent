# 液压系统外部基准（Track B）HYDRAULIC_SYSTEMS_BENCHMARK

> 本文是 Track B 外部基准的权威说明（中文优先）。它记录对 UCI 液压系统状态监测数据集的
> 独立、确定性评估，与 Track A（受控合成数据）解耦。原始结果见生成报告
> `docs/EVALUATION_REPORT_EXTERNAL_HYDRAULIC.md`（英文生成物）。本文与代码、生成报告
> 三者口径保持一致，任何结论都以本文的「测试了什么 / 不测试什么」为边界。

## Dataset

- 名称：`condition-monitoring-of-hydraulic-systems`（UCI Machine Learning Repository，数据集 #447）。
- 来源：<https://archive.ics.uci.edu/static/public/447/condition+monitoring+of+hydraulic+systems.zip>
- DOI：`10.24432/C5CW21`；许可证：`CC BY 4.0`。
- 引用：Helwig, N., Pignanelli, E., & Schütze, A. (2015). *Condition monitoring of
  hydraulic systems* [Dataset]. UCI Machine Learning Repository.
- 文件包 SHA-256：`24128aad2ee45eea7e6b63ebbd9992cdf25d0483a2cebefbfc13bc69079af1f2`。
- 结构：扁平 zip，共 20 个成员 = `description.txt`、`documentation.txt`、`profile.txt` +
  **17 个传感器数据文件**。
- 循环：**2205 次 60 秒工作循环**；其中 **1449 次稳定（stable code 0）用于主基准**，
  756 次非稳定循环被排除。
- 传感器：17 个文件中仅 **14 个物理传感器**用于主基准——`PS1`–`PS6`、`EPS1`
  （100 Hz / 6000 采样点）、`FS1`–`FS2`（10 Hz / 600 采样点）、`TS1`–`TS4`、`VS1`
  （1 Hz / 60 采样点）；`CE`（冷却效率）、`CP`（冷却功率）、`SE`（效率因子）是
  虚拟/效率传感器，**被排除**。
- `profile.txt` 每个 cycle 的五列官方标签如下；数值含义不按匿名特征猜测：

  | component / flag | raw code → official meaning |
  |---|---|
  | Cooler | `3` close to total failure；`20` reduced efficiency；`100` full efficiency |
  | Valve | `73` close to total failure；`80` severe lag；`90` small lag；`100` optimal switching behavior |
  | Internal pump leakage | `0` no leakage；`1` weak leakage；`2` severe leakage |
  | Hydraulic accumulator | `90` close to total failure；`100` severely reduced pressure；`115` slightly reduced pressure；`130` optimal pressure |
  | Stable flag | `0` conditions were stable；`1` static conditions might not have been reached yet |

- 第一阶段 condition targets 只选择 `cooler`（3 类）与 `valve`（4 类）；pump / accumulator
  保留在 complete-profile group 中防 leakage，stable flag 只用于主基准过滤，不作为模型 feature 或 target。

## Why This Dataset

- **外部真实传感器数据**：来自液压测试台，不是本项目的合成数据；它为一个独立条件分类任务
  增加非合成证据，但**不会**消除 Track A RCA top-k 的同源循环。
- **官方、公开、可复现**：固定 URL + 固定 SHA-256 + 明确许可证（CC BY 4.0），任何人都能
  下载同一份字节流并复现结果。
- **多类条件状态**：`cooler`/`valve` 各自有多个离散条件码，适合做有 ground truth 的
  分类与 profile-group-held-out 插值验证，且能暴露当前表示下的类别混淆（如 valve 的 `80`↔`90`）。
- **条件分类独立于 RCA**：条件码是可客观度量的中间状态，验证「摄取 → 特征 → 分类 →
  证据」链路，而不触碰 Track A 才能回答的「为什么坏、该开什么工单」。

## Scope

- 只验证：数据摄取（下载 / SHA 硬校验 / 安全解压 / 必需文件校验）、特征提取、
  **条件分类（condition classification）**、**同一台架 stable regime 的 profile-group-held-out 插值**、以及
  **typed diagnostic evidence**（`DiagnosticEvidence → EvidenceItem`）的契约集成。
- 代码上**与 Track A 解耦**：`src/benchmarks/hydraulic.py` 不 import 任何 Track A 模块
  （`src.agent`、`src.evaluation`、`src.contracts`、`src.db`）。
- 证据集成侧只挂 DIAGNOSTIC 证据、产出**非因果**的条件假设，不产出根因结论或动作提案。
- 第一阶段控制在两个 target：Cooler 提供 3 类效率状态，Valve 提供 4 类切换滞后状态；Pump 与
  Accumulator 不参与本轮分类结果声明，后续只有在保持相同 split/evidence 纪律时才扩展。

## What This Benchmark Tests

- **摄取**：URL 下载 → SHA-256 硬校验（不匹配即失败）→ zip-slip 安全解压 → 成员数校验 →
  必需文件校验，且幂等（已存在则跳过）。
- **特征**：14 个物理传感器 × 4 个统计量 = 56 个特征，数量与命名由配置契约锁定。
- **条件分类**：`cooler` 与 `valve` 两个目标，各跑 Logistic 与随机森林两个固定超参家族。
- **划分正确性**：complete-profile 分组划分，组与循环都不跨集，每集都覆盖全部类别；
  不做随机 cycle 级回退（找不到合法划分即显式报错）。
- **group-held-out 评估**：模型只在训练集 fit；验证集只用于选型；测试集只报告一次，两个固定配置的
  结果都不改动地保留。
- **证据契约**：诊断预测转为 `EvidenceSourceType.DIAGNOSTIC` 的 `EvidenceItem`，稳定
  `source_id`、`citation`、非因果 `metadata`，且缺失/矛盾输入触发 fail-closed 行为。

## What It Does NOT Test

- **不做完整 RCA**：不诊断失效根因、不做失效因果链，也不做任何因果证明（causal proof）。
- **不生成 / 不推荐工单**：不产出 `ProposedAction`，不写任何 CMMS / 维护系统。
- **不读取 / 不检索文档**：不跑 RAG、不使用 `data/docs/*.md`，与检索、claim grounding 无关。
- **不验证工厂部署**：结果是公开数据集的离线分数，不是现场 / 台架 / 生产性能。
- **不验证校准概率**：`model_score` 是未校准的分类器输出，不是可信概率估计。
- **不验证 Track A 的 planner / synthesizer / 审批门 / 场景评估**：那些能力仍由 Track A 覆盖。

## Data Preparation

入口：`scripts/prepare_hydraulic_benchmark.py`（薄 CLI，核心在 `src/benchmarks/hydraulic.py`）。

- 校验 `profile.txt` 形状（2205 × 5）与列名（`cooler, valve, pump, accumulator, stable`）。
- 校验每个 profile 列只出现官方码集合（如 `stable ∈ {0,1}`）。
- 校验每个传感器文件形状（行数 = 2205，列数 = 该传感器每循环采样点数）。
- 校验稳定循环计数必须等于 1449，否则报错。
- 一次只读入一个传感器矩阵（`read_sensor_matrix`）以限制内存，再释放。
- 输出（**忽略，不入库**）：
  - `data/processed/hydraulic/features.csv`
  - `data/processed/hydraulic/prepare_manifest.json`
  - `data/processed/hydraulic/split_manifest.json`

## Feature Extraction

- 在**稳定循环窗口**内，对每个传感器计算 4 个标量：`mean`、`std`（总体标准差，`ddof=0`）、
  `min`、`max`。
- 特征数量 = 14 传感器 × 4 = **56**。
- 特征命名：`{SENSOR}__{fn}`，例如 `PS1__mean`、`FS2__std`。
- 特征矩阵只取稳定循环（`stable == 0`），行数为 1449；`cycle` 列保留 1 基的公开周期号，
  便于溯源 UCI 文档。

## Train / Validation / Test

- 稳定循环共 1449 次，按 **complete-profile group** `(cooler, valve, pump, accumulator)`
  分组，共 **144 组**。
- 划分按**组**进行，组与循环都不跨集，目标比例约 60/20/20，且每个集合都必须覆盖
  `cooler` 与 `valve` 的全部类别；确定性搜索（`seed=447`），找不到合法划分即报错，
  **不回退到随机 cycle 级划分**。
- 实际划分（确定性，`seed=447`）：

  | 集合 | 循环数 | 组数 |
  |---|---|---|
  | train | 860 | 86 |
  | val | 299 | 29 |
  | test | 290 | 29 |

- 训练只在 `train` 上进行；`val` 仅用于按 macro-F1 选 preferred family；`test` 只在最终
  报告一次。`seed`：模型与划分都用 `447`。
- 这是同一台架 stable regime 内的随机 profile-group split，不是时间切分；相邻 cycle 的时间自相关
  可能仍跨 split。290 个 test cycles 聚合在 29 个 groups 中，不能当 290 个独立样本解释；报告因此
  追加按 group 重采样的 Macro-F1 95% bootstrap 区间。

## Models

两个固定超参的 sklearn `Pipeline`（不调参、不搜参）：

- **Logistic**：`SimpleImputer(strategy="median")` → `StandardScaler()` →
  `LogisticRegression(max_iter=2000, class_weight="balanced")`。
- **Random forest**：`SimpleImputer(strategy="median")` →
  `RandomForestClassifier(n_estimators=300, class_weight="balanced_subsample")`。

选型：每个目标取验证集 macro-F1 最高的固定配置为 preferred；若并列，按配置顺序确定用于 evidence
adapter 的实现（Cooler 为并列，不表示 Logistic 更好）。测试集两个固定配置的结果**都不改动**地
一并报告。模型序列化到 `artifacts/benchmarks/hydraulic/models/*.joblib`（忽略，不入库），
并记录模型文件 SHA-256 与 `model_version`（如 `uci447-valve-logistic-v1`）。

## Metrics

测试集报告以下指标（硬分类结果，未校准）：

- `accuracy`、`balanced_accuracy`、`macro_f1`、`weighted_f1`。
- 每个类别的 `precision` / `recall` / `f1` / `support`。
- 混淆矩阵（行 = 真实，列 = 预测）。
- 验证集 `macro_f1` 仅用于选型，不用于结果声明。

## Results

同一台架 stable-only profile-group-held-out 结果（生成报告 `docs/EVALUATION_REPORT_EXTERNAL_HYDRAULIC.md`）：

- **`cooler`**：两个固定配置的 `accuracy` / `macro-F1` 均为 **1.0**，验证集也并列；这说明
  当前表示/划分下任务可分，不是更强的因果或现场诊断证据，也没有 repeated split / sensor ablation 支撑。
- **`valve`**（preferred = logistic，按验证集 macro-F1 选出）：

  | family | test accuracy | test macro-F1 |
  |---|---|---|
  | logistic | **0.5897** | **0.5692**（该 split 的 preferred） |
  | random_forest | 0.4276 | 0.4515 |

- **`valve` / logistic 每类 F1**（负结果保留）：

  | class | code | f1 |
  |---|---|---|
  | close_to_total_failure | 73 | 0.5250 |
  | severe_lag | 80 | 0.4359 |
  | small_lag | 90 | 0.4557 |
  | optimal_switching_behavior | 100 | 0.8602 |

- **保留的负结果与混淆**：当前表示下 valve 的 `severe_lag(80)` 与 `small_lag(90)` 出现明显混淆——logistic 把
  100 个 `80` 中的 46 个判为 `90`，把 70 个 `90` 中的 12 个判为 `80`、14 个判为 `100`；
  随机森林同样把大量 `80` 判为 `90`、大量 `100` 判为 `90`。这些数字**不做任何美化**，
  完整混淆矩阵见生成报告。

## Evidence Integration

- `DiagnosticEvidence` 契约把一次预测建模为**非因果**的条件分类：`predicted_condition_code`、
  `predicted_condition_label`、未校准 `model_score`、`global_top_feature_values`、
  `model_version`、`source_cycle` 与 `provenance`。
- 转成 `EvidenceItem` 时 `source_type=DIAGNOSTIC`，`source_id` 稳定且跨组件/模型版本唯一：
  `diagnostic:{dataset_id}:{component}:{source_cycle}:{model_version}`；`citation` 与
  `source_id` 一致；`metadata.causal_status = "non_causal_condition_classification"`。
- `global_top_feature_values` 是按模型全局重要性选出的五个 feature 在该 cycle 的原始取值；它没有
  class-specific sign、baseline 或 local contribution，**不是**预测类别的局部支撑解释。
- 未校准 `model_score` 不映射成 ordinal Agent confidence；Track B 假设固定为 `LOW`。
- 集成规则（fail-closed）：无诊断证据 → 显式 abstain（无假设、无动作）；同一组件的多个
  预测出现矛盾条件码 → 该组件 abstain（不产出假设）。

## Agent-side Evaluation

12 个确定性契约场景：**8 个真实 profile-group-held-out test 预测 + 2 个缺失证据 abstain + 2 个合成矛盾**。

- 8 个真实场景由「cycle hash + 类别覆盖」选择（每个真实类别取一个 + 额外 seeded 周期），
  选择过程**不依赖预测正确性或分数**；ground truth 只用于选择记录，**不进入 Agent 证据
  provenance**。
- 8 个真实场景中包含一个**自然的 valve `80→90` 误分类**（cycle 265：真实 `severe_lag(80)`
  被预测为 `small_lag(90)`），如实保留。
- 检查结果（`evidence_integration.json`，忽略不入库）：

  | check | result |
  |---|---:|
  | evidence_attached | 12 |
  | citation_valid | 12 |
  | abstention_correct | 4 |
  | contradiction_handled | 2 |
  | unique_ids | 12 |
  | hypothesis_evidence_id_presence_rate | 1.0 |
  | semantic_unsupported_claim_rate | `not_measured_no_entailment_annotations` |

- **口径**：以上是**契约检查**（typed 证据挂载、citation id 存在、abstain 正确、矛盾处理、
  唯一 id），**不是诊断正确性**。没有独立 entailment annotations，因此 semantic unsupported
  claim rate 明确为 `not_measured_no_entailment_annotations`；它不验证预测对不对，也不验证 RCA、工单推理
  或因果正确性。

## Failure Cases

- **valve `80`↔`90` 观察到混淆**：logistic 把 46/100 的 `severe_lag(80)` 判为 `small_lag(90)`；
  可能原因包括统计特征压缩、group shift、模型配置、传感器排除或标签语义，尚无 ablation 可归因。
- **valve 整体负结果**：logistic macro-F1 仅 0.5692、随机森林 0.4515，均显著低于 cooler 的
  1.0；这是诚实保留的泛化结果，说明 valve 状态在 56 个标量特征下难以完全区分。
- **被排除的虚拟传感器**：`CE`/`CP`/`SE` 未用于主基准，故结果不能外推到「效率相关」的诊断。

## Limitations

- **不证明 RCA / 因果**：条件分类正确 ≠ 根因诊断正确；本项目不做因果证明。
- **不证明生产可用**：离线公开数据结果，不构成现场 / 工厂部署能力。
- **分数未校准**：`model_score` 是未校准分类器输出，不能当概率读。
- **单数据集**：只在一个液压测试台上验证，泛化边界有限；换设备/工况需重跑重审。
- **stable-only 选择**：排除 756 个未达到静态条件的 cycles，结果只适用于稳定工况，可能让 Cooler
  更容易分类；不覆盖启动/切换/过渡状态。
- **目标 proxy 控制**：CE/CP/SE 是派生效率量，因可能接近目标定义而排除；当前结果只基于 14 个物理传感器。
- **时间自相关**：complete-profile groups 不跨 split，但不是 chronological split，相邻 cycles 仍可能
  跨 split；group bootstrap 区间缓解了 cycle 独立性误读，但没有消除此风险。
- **名义化建模**：官方条件码描述有序退化程度，本轮按多类 nominal classification 处理，未报告
  ordinal error / MAE；这是任务定义限制，不是标签无序的声明。
- **特征丢弃时序结构**：只用均值/标准差/最小/最大四个标量，不保留采样序列内的时间演化。
- **选型在验证集上、测试只报一次**：诚实但仍有模型与数据双重方差，结果不应过拟合解读。
- **证据检查是契约级**：`evidence_*` 检查验证的是 typed 证据与 abstain/矛盾处理的契约行为，
  **不是**诊断正确性，也不是 RCA / 工单 / 文档 / 因果能力。
- **与 Track A 互不替代**：Track B 的数据与 classifier harness 独立；evidence integration 有意复用
  `AgentState` / `Hypothesis` / `EvidenceItem` contracts。Track A 保留 25 资产、180 天、30 场景、
  当前指标、工作流、安全与边界场景，结果不能互相代替。

## Reproduction

测试基线：本轮前 `71 passed`；加入 Track B core 与 evidence/integration 测试后 `114 passed`
（新增 43）。Track A 的 30 场景与原指标保持不变。

在项目根目录按序执行（PowerShell，使用项目虚拟环境）：

```powershell
.\.venv\Scripts\python scripts\download_hydraulic_dataset.py
.\.venv\Scripts\python scripts\prepare_hydraulic_benchmark.py
.\.venv\Scripts\python scripts\run_hydraulic_benchmark.py
```

- `download_hydraulic_dataset.py`：下载并解压原始数据（SHA-256 硬校验，幂等）。
- `prepare_hydraulic_benchmark.py`：校验原始数据并生成特征与划分 manifest。
- `run_hydraulic_benchmark.py`：训练、选型、报告测试结果，写生成报告并跑 12 个证据集成场景。

路径与版本控制策略（详见 `.gitignore`）：

| 路径 | 类别 | 说明 |
|---|---|---|
| `configs/benchmarks/hydraulic_systems.yaml` | 提交 | 唯一权威配置（URL / SHA / 传感器 / 目标 / 划分 / 模型 / 报告路径） |
| `data/raw/hydraulic/` | 忽略 | 原始下载 + 解压（含 zip 与 20 个成员文件） |
| `data/processed/hydraulic/` | 忽略 | `features.csv` + `prepare_manifest.json` + `split_manifest.json` |
| `artifacts/benchmarks/hydraulic/` | 忽略 | `metrics.json`、`run_manifest.json`、`test_predictions.csv`、`evidence_integration.json`、`models/*.joblib` |
| `docs/EVALUATION_REPORT_EXTERNAL_HYDRAULIC.md` | 生成但提交 | 由 `run_hydraulic_benchmark.py` 生成并追加 Evidence Integration 段 |

交叉引用：Track A 方法学见 `docs/EVALUATION_METHODOLOGY.md`；能力状态见
`docs/CAPABILITY_MATRIX.md`；系统手册见 `docs/HANDBOOK.md`；后续计划见 `docs/NEXT_PHASES.md`。
