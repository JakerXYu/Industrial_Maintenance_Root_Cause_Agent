# 能力矩阵 Capability Matrix

> 逐项对照当前实现事实，每项一个独立行，标注状态、证据路径与目标处置。状态语义：
> `IMPLEMENTED`=已实现并有测试/代码证据；`PARTIAL`=已实现但存在缺陷、边界或仅为隐式/代理；
> `MISSING`=当前完全不存在；`OUT OF SCOPE`=仅用于明确记录为「刻意非目标」的项（如长期记忆、
> 真实写、向量 DB），并给出准确限定；其余缺失的核心目标一律记为 `MISSING`。
> 处置：`保持`=维持现状；`加固`=补齐约束/测试/真实语义；`新增`=后续实现；`延后`=条件满足才做。

事实基线：确定性 baseline（未接 LLM）；固定 plan；只读工具；SQLite；114 测试；30 场景（Track A）；
评估为 **7 项指标 + `total_scenarios` 计数**（不是 8 项指标，仅 Track A）。
另有 Track B 外部基准（UCI #447）独立验证摄取/特征/条件分类/held-out/typed 证据契约。
来源：`../README.md`、`docs/HANDBOOK.md`、`docs/NEXT_PHASES.md`（P0/P1/P2 路线图）、
`docs/EVALUATION_REPORT.md`、`docs/EVALUATION_REPORT_EXTERNAL_HYDRAULIC.md`、
`docs/benchmarks/HYDRAULIC_SYSTEMS_BENCHMARK.md`。

## 1. Agent Runtime（智能体运行时）

| 能力项 | 状态 | 证据路径 | 目标处置 |
|---|---|---|---|
| State（状态） | IMPLEMENTED | `src/contracts/agent.py` `AgentState`（request_id/user_question/asset_id/evidence/tool_calls/hypotheses/pending_action/status/final_answer） | 保持 |
| Node（节点） | PARTIAL | 无显式 node 对象；`src/agent/runner.py` 内联 interpret/plan/execute/synthesize 为顺序步骤（隐式线性节点） | 加固（P0-3 显式化） |
| Edge（边） | PARTIAL | 无显式边/迁移定义；状态仅靠 `AgentStatus` 字段顺序推进，无迁移表 | 加固（P0-3 合法迁移） |
| Graph / State Machine（图 / 状态机） | PARTIAL | 隐式线性状态机（`AgentStatus` enum + runner 顺序编排），非图（无分支/循环） | 加固（P0-3 显式状态机） |
| Checkpoint（检查点） | MISSING | 无状态快照/恢复；`src/agent/tracing.py` 只落 `TraceRecord`，非 checkpoint | 新增（P0-3） |
| Termination condition（终止条件） | PARTIAL | 固定序列跑完设 COMPLETE，解析失败/异常设 ERROR 并跳过后续阶段；无 step budget、deadline 或循环终止谓词 | 加固（P0-3 终态语义） |
| Retry（重试） | MISSING | `src/agent/runner.py`/`executor.py` 无任何 retry | 新增（P0-3 retry 上限） |
| Timeout（超时） | MISSING | 无 timeout 预算 | 新增（P0-3） |
| Fallback（兜底） | MISSING | `runner.py` 的 `try/except` 仅是优雅降级为 ERROR，非 fallback 策略 | 新增（P0-2 fake/fallback） |
| Recovery（恢复） | PARTIAL | `recovery_rate` 仅断言边界场景到达期望终态（error/complete/pending），是场景级代理，非运行时重试/恢复 | 加固（P0-6 真实 recovery） |

## 2. Tool Calling（工具调用）

| 能力项 | 状态 | 证据路径 | 目标处置 |
|---|---|---|---|
| Tool Calling（工具调用） | PARTIAL | `ToolRegistry.call()` 可执行 4 个只读工具，但 plan 固定；没有模型驱动的动态 tool selection/calling | 加固（P0-2） |
| Tool schema（工具 schema） | PARTIAL | `schemas()` 声明 JSON schema，但 `call()` 直接 `self._tools[name](**args)`，不按 schema 校验 | 加固（P0-3 schema enforcement） |
| Parameter validation（参数校验） | PARTIAL | 工具内部部分校验（非法参数返回 `INVALID_ARGUMENT`）；注册表不做 schema 校验 | 加固 |
| Permission（权限） | PARTIAL | 读工具自动执行；写类动作经审批门（`src/agent/policy.py`）；无 per-tool 授权、无认证 | 加固（写前 blocker / P1） |
| Read-only / write separation（读写分离） | IMPLEMENTED | 只读工具 + `ProposedAction` 门禁 + v0 无外部写（`policy.py`） | 保持 |
| Idempotency（幂等） | PARTIAL | 当前只读查询天然可重复执行；审批、invocation ledger 和未来副作用无幂等 key、锁或去重 | 加固（P0-3 / 写前 blocker） |
| Error handling（错误处理） | PARTIAL | `ToolResult` 错误码（`ToolErrorCode`）+ empty≠error；但无重试/超时/兜底 | 加固（P0-3） |
| Tool result normalization（结果规范化） | IMPLEMENTED | `ToolResult[T]`（ok/data/error/empty）+ `executor._meta` 归一为 status/count/payload | 保持 |

## 3. RAG（检索增强）

| 能力项 | 状态 | 证据路径 | 目标处置 |
|---|---|---|---|
| Document parsing（文档解析） | PARTIAL | `load_documents` 只读取 UTF-8 Markdown；无 PDF/HTML/表格/front matter 解析 | 加固（按语料需求） |
| Chunking（分块） | IMPLEMENTED | `chunk_markdown`（heading-aware + section 内滑动窗口 + overlap） | 保持 |
| Metadata（元数据） | PARTIAL | `DocumentChunk` 有 document/section/start_line/end_line/chunk_id，无更丰富来源元数据 | 加固（P0-4 来源元数据） |
| Embedding（嵌入） | OUT OF SCOPE | 向量/embedding 明确非 v0 目标（NEXT_PHASES 非目标、README 非目标）；P2-2 条件化才评估 | 延后（P2-2） |
| Vector retrieval（向量检索） | OUT OF SCOPE | 向量数据库明确非目标（同上） | 延后（P2-2） |
| BM25 | MISSING | 当前仅 token-overlap 关键词检索（`src/rag/retriever.py`），无 BM25/FTS | 新增（P0-4） |
| Hybrid retrieval（混合检索） | MISSING | 无 | 延后（P2-2） |
| Rerank（重排序） | MISSING | 无 | 延后（P2-2） |
| Citation / grounding（引文 / 依据） | PARTIAL | `EvidenceItem.source_id/citation` + `Hypothesis.supporting/contradicting_evidence_ids` 存在；但 supporting 无差别挂全部证据（弱 grounding），meter 用单一 `meter_summary:{asset_id}` 造成重复证据 id | 加固（P0-5 claim 级 grounding） |

## 4. Memory（记忆）

| 能力项 | 状态 | 证据路径 | 目标处置 |
|---|---|---|---|
| Working memory（工作记忆） | IMPLEMENTED | `AgentState`（单次运行内的 evidence/tool_calls/hypotheses） | 保持 |
| Conversation / task state（会话 / 任务状态） | PARTIAL | 单次 task state 由 `AgentState` 承载；无跨请求 conversation history，task state 也不持久化 | checkpoint 见 P0-3；conversation 见 P2-3 |
| Summary memory（摘要记忆） | MISSING | 无摘要 | 新增（P2-3） |
| Long-term memory（长期记忆） | OUT OF SCOPE | 明确非目标（NEXT_PHASES 非目标、README 非目标）：除非多轮会话需要且先完成隐私/保留策略 | 延后（非目标触发条件满足才评估） |
| Memory retrieval（记忆检索） | MISSING | 无记忆子系统，无检索 | 新增（条件化） |
| Expiration / update（过期 / 更新） | MISSING | 无 | 新增（条件化） |

## 5. Evaluation（评估）

| 能力项 | 状态 | 证据路径 | 目标处置 |
|---|---|---|---|
| Task Success Rate（任务成功率） | MISSING | 未计算；仅有 asset resolution + root-cause | 新增（P0-6） |
| Tool Selection Accuracy（工具选择准确率） | PARTIAL | `src/evaluation/metrics.py` 已实现，但固定 plan 恒为 required_tools 超集，恒 1.0（静态代理） | 加固（P0-6 precision/recall） |
| Tool Argument Accuracy（工具参数准确率） | MISSING | 未计算 | 新增（P0-6） |
| Evidence Recall（证据召回） | PARTIAL | 已实现，0.3698（`docs/EVALUATION_REPORT.md`）；主因 gold 事件证据（EV-*）不可达（无 events 工具）+ WO 查询窗口/limit + executor 截断 | 加固（P0-6 + 补事件/维护工具） |
| Citation Precision（引文精度） | MISSING | 未计算 | 新增（P0-6） |
| Unsupported Claim Rate（无依据主张率） | MISSING | 未计算 | 新增（P0-6 + P0-5 abstention） |
| Root Cause Top-K（根因 Top-K） | PARTIAL | top1/top3 已实现，但与生成逻辑同源（循环，见 EVALUATION_METHODOLOGY） | 加固（held-out 破环，P0-6） |
| Recovery Rate（恢复率） | PARTIAL | 场景级终态断言（error/complete/pending），非重试/恢复（代理） | 加固 |
| Latency（延迟） | PARTIAL | `total_latency_ms` 与工具 `latency_ms` 已记录（`TraceRecord`/`ToolCallTrace`），但未作为评估指标汇总报告 | 加固（P0-6） |
| Token / API Cost（Token / 成本） | MISSING | 无 LLM，无成本 | 新增（P0-6） |
| External benchmark（外部基准，Track B） | IMPLEMENTED | `src/benchmarks/hydraulic.py` + `scripts/*_hydraulic_benchmark.py`；摄取/特征/条件分类/held-out/typed 证据契约；结果见 `docs/EVALUATION_REPORT_EXTERNAL_HYDRAULIC.md` | 保持（不扩展到 RCA/工单/文档/生产声明） |

> Track B 只验证「摄取 → 特征 → 条件分类 → held-out → typed 诊断证据契约」，**不**验证完整 RCA、
> 工单生成、文档检索、工厂部署或因果证明；其 `evidence_*` 检查是契约检查，不是诊断正确性。
> 权威边界见 `docs/benchmarks/HYDRAULIC_SYSTEMS_BENCHMARK.md`。

## 6. Safety（安全）

| 能力项 | 状态 | 证据路径 | 目标处置 |
|---|---|---|---|
| Prompt injection（提示注入） | PARTIAL | 有 `prompt_injection` 场景（`scenarios.py`）；确定性基线把 retrieved 文档当 data，非 LLM 后真实防御证明 | 加固（P1-1） |
| Untrusted tool output（不可信工具输出） | PARTIAL | retrieved 文档当 data（不当指令）；但无 schema/白名单校验（无 LLM 故当前攻击面小） | 加固（P1-1） |
| Permission boundary（权限边界） | PARTIAL | read 自由 / write 审批门；无认证授权 | 加固（写前 blocker） |
| Unsafe write request（不安全写请求） | PARTIAL | `execute_pending_action` 非 APPROVED 抛 `PermissionError` + `unauthorized_write` 场景；v0 无外部写 | 保持（写前 blocker 后升级） |
| Human approval（人工审批） | PARTIAL | approve/reject 端点存在（`src/api/main.py`）；但无认证、内存态、可逆、无终态 | 加固（P1-2 + 写前 blocker） |
| Audit log（审计日志） | MISSING | 无审计；`TraceRecord` 不含 `approved_by`/`approved_at`/审批结果 | 新增（P1-2） |

## 7. Production Engineering（生产工程）

| 能力项 | 状态 | 证据路径 | 目标处置 |
|---|---|---|---|
| Logging / tracing（日志 / 追踪） | PARTIAL | trace 有（`src/agent/tracing.py` 落 `TraceRecord`，可观测性/诊断记录，非审计）；结构化日志无 | 加固（P1-3） |
| Config（配置） | IMPLEMENTED | `src/config.py` `Settings` + 环境变量 + `SecretStr`；`.env.example` | 保持 |
| Error handling（错误处理） | PARTIAL | `ToolResult` 错误码 + `runner` 降级 ERROR；无重试/兜底 | 加固（P0-3） |
| Reproducible test cases（可复现用例） | IMPLEMENTED | 固定 seed 生成 + 114 测试 + 30 个 Track A 场景 + 12 个 Track B evidence 场景 | 保持 |
| Unit / integration / eval tests（单测 / 集成 / 评估） | IMPLEMENTED | `tests/` 114 用例跨层 + 双轨离线评估 | 保持 |
| Docker | PARTIAL | Dockerfile/Compose 存在且 config 通过；Historical base 镜像曾 healthy，但 Current Track B 依赖镜像因 daemon 不可用未重建验证 | 补 current build/health + CI gate |
| API | IMPLEMENTED | `src/api/main.py`（FastAPI） | 保持 |
| CLI or UI（命令行或界面） | IMPLEMENTED | `ui/streamlit_app.py`（Streamlit）；无 CLI | 保持 |

## 8. External Benchmark（外部基准，Track B）

> 本节只登记**已真实存在并被测试覆盖**的 Track B 代码（UCI #447 液压基准）。证据路径均指向
> `src/benchmarks/hydraulic.py`、`src/contracts/evidence.py`、`src/evaluation/diagnostic_integration.py`。
> 结果与权威边界见 `docs/EVALUATION_REPORT_EXTERNAL_HYDRAULIC.md` 与
> `docs/benchmarks/HYDRAULIC_SYSTEMS_BENCHMARK.md`。本表**不**升级任何 LLM / RAG / retry /
> checkpoint / memory / 语义 grounding 相关项——那些项仍按上文 §1–§4 的现状记录，不因 Track B 改变。

| 能力项 | 状态 | 证据路径 | 目标处置 |
|---|---|---|---|
| External data adapter（外部数据摄取适配器） | IMPLEMENTED | `src/benchmarks/hydraulic.py` `download_and_extract`（std-lib 下载 + SHA-256 硬校验 + 原子替换 + zip-slip 安全解压 + 必需文件校验，幂等） | 保持（不扩展到 RCA/工单/生产） |
| Multi-rate sensor parser（多采样率传感器解析） | IMPLEMENTED | `src/benchmarks/hydraulic.py` `read_sensor_matrix`（一次只读一个传感器矩阵；三档采样率 100 Hz/6000、10 Hz/600、1 Hz/60） | 保持 |
| Feature extraction（特征提取） | IMPLEMENTED | `src/benchmarks/hydraulic.py` `compute_features` + `feature_names`（14 物理传感器 × 4 统计量 mean/std ddof=0/min/max = 56 特征） | 保持 |
| Profile-group split（按配置组划分） | IMPLEMENTED | `src/benchmarks/hydraulic.py` `split_groups` / `_greedy_group_split`（complete-profile group 与循环均不跨集，60/20/20，seed=447，覆盖全部类别，不回退随机 cycle） | 保持 |
| Diagnostic classifier（诊断条件分类器） | IMPLEMENTED | `src/benchmarks/hydraulic.py` `make_logistic_pipeline` / `make_random_forest_pipeline` + `run`（固定超参 sklearn pipeline；验证集 macro-F1 选型，测试集只报一次） | 保持 |
| Diagnostic evidence contract（诊断证据契约） | IMPLEMENTED | `src/contracts/evidence.py` `DiagnosticEvidence` → `to_evidence_item`（`source_type=DIAGNOSTIC`、稳定 `source_id`、`causal_status=non_causal_condition_classification`） | 保持 |
| Evidence integration（证据集成） | IMPLEMENTED | `src/evaluation/diagnostic_integration.py` `integrate_diagnostic_evidence`（DIAGNOSTIC 证据挂载 → `AgentState` → 非因果 `Hypothesis` / fail-closed abstain，无 `ProposedAction`） | 保持 |
| Held-out external evaluation（外部留出评估） | IMPLEMENTED | `src/evaluation/diagnostic_integration.py` `evaluate_diagnostic_integration` / `evaluate_hydraulic_prediction_evidence`（12 确定性契约场景 = 8 真实 + 2 缺失 + 2 矛盾；7 项契约检查） | 保持（不扩展到语义 grounding / RCA 正确性） |

## 交叉引用

- 系统实现细节：`docs/HANDBOOK.md`
- P0/P1/P2 路线图与非目标：`docs/NEXT_PHASES.md`
- 评估结果（Track A）：`docs/EVALUATION_REPORT.md`
- 评估结果（Track B）：`docs/EVALUATION_REPORT_EXTERNAL_HYDRAULIC.md`
- 外部基准权威说明（Track B）：`docs/benchmarks/HYDRAULIC_SYSTEMS_BENCHMARK.md`
- 外部证据集成链路（Track B）：`docs/EXTERNAL_EVIDENCE_INTEGRATION.md`
- 指标定义与局限：`docs/EVALUATION_METHODOLOGY.md`
- 安全威胁建模：`docs/SAFETY_AND_THREAT_MODEL.md`
- 面试答辩：`docs/INTERVIEW_GUIDE.md`
