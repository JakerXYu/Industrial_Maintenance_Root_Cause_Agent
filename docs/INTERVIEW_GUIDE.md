# 面试/答辩指南 INTERVIEW_GUIDE

> 30–60 分钟叙述稿 + 演示脚本 + 架构权衡 + 深度问题强答 + 一个失败案例 +
> 诚实指标口径 + 非目标防御。面向技术面试官或项目评审。事实均与代码一致，
> 配套证据：`../README.md`、`docs/HANDBOOK.md`、`docs/CAPABILITY_MATRIX.md`、
> `docs/EVALUATION_METHODOLOGY.md`、`docs/SAFETY_AND_THREAT_MODEL.md`、`docs/EVALUATION_REPORT.md`。

## 1. 30–60 分钟叙述线（narrative）

1. **一句话定位**（1 分钟）：不是“维修聊天机器人”，而是可验证、可观测、可优雅降级、可审批的
   工业 Agent Harness；LLM 是概率推理组件，外围是确定性软件系统。注意口径：当前是**优雅错误处理**
   （异常降级为 `ERROR`、不崩），**不是**可恢复——无 checkpoint/retry/resume，不能从失败点恢复或重放。
2. **现状如实说明**（2 分钟）：当前是确定性 baseline，**未接 LLM**；固定 plan + 规则打分，
   端到端可跑（数据→契约→只读工具→分析→document retrieval / RAG scaffold→agent→API/UI）。Docker Compose 已在本机构建、运行并通过 API/UI 健康检查，但不是生产部署证明。
3. **架构分层**（5 分钟）：契约（Pydantic，叶子层）→ 数据（只读 SQLite，参数化 SQL）→
   只读工具（ToolResult，empty≠error）→ 分析（趋势/异常）→ document retrieval / RAG scaffold（heading-aware 分块 + 关键词检索）
   → agent（typed state + linear orchestration + 审批门 + trace）→ 评估（30 场景 + 7 项指标，另含场景总数）→ API/UI；Docker 是待验证部署产物。
4. **核心原则**（3 分钟）：LLM 不是 system of record；empty≠error；read 自由、write 审批；
   evidence contracts first，grounding 尚未闭环；typed everywhere。
5. **安全模型**（5 分钟）：只读工具自动执行；写类动作先产出 `ProposedAction`，显式 APPROVE 才可执行；
   v0 无外部写；request_id 严格校验 + 路径包含；密钥 SecretStr；并诚实列出非保证。
6. **评估与局限**（5 分钟）：71 测试、30 场景、7 项指标（另含场景总数）；诚实说明
   evidence_recall=0.3698（gold 事件证据不可达 + WO 窗口/截断），以及 top-k/tool-selection/safety/recovery
   的循环/静态/代理性质。
7. **下一步**（3 分钟）：按 `docs/NEXT_PHASES.md` 的 P0/P1/P2 路线图讲：
   P0（可复现基线+CI、有界可选真实 LLM+确定性 fallback、显式 runtime+checkpoint+调用账本、
   BM25/FTS 检索、唯一证据 ID+claim 级 grounding、held-out 非循环评估）；
   P1（prompt-injection/不可信输出安全、持久化审批审计、日志+容器真实验证、检索实验）；
   P2（条件化 LangGraph、embeddings/hybrid/rerank、多轮摘要、OpenTelemetry、沙箱 CMMS 适配器）。
   真实写前的 blocker 清单不变。

## 2. 演示脚本（demo script）

按此顺序演示，每个步骤先点题再操作：

1. 生成/导入可复现数据：`python scripts/generate_synthetic_data.py` + `load_database.py`（固定 seed）。
2. `pytest`（71 全绿）→ `run_evaluation.py` 生成 `docs/EVALUATION_REPORT.md`。
3. 起 API：`uvicorn src.api.main:app`，打开 `/docs`：
   - `GET /health`；`GET /assets/A001`；`GET /work-orders?asset_id=A001`；`GET /meter-summary?asset_id=A001`。
   - `POST /agent/query`（问题 `A001 stopped this week...`），展示返回的 `AgentState`：
     `pending_action.status == PENDING_APPROVAL`、`hypotheses` 带证据 id。
   - `POST /actions/{id}/approve` 展示 APPROVED + `approved_by`/`approved_at`；再演示 reject 清空 `approved_at`。
   - `GET /traces/{id}` 展示 trace。
4. 起 UI：`streamlit run ui/streamlit_app.py`，按“资产与数据 → Agent 任务 → 运行记录 → 使用说明”演示中文工作流。
5. 关键“安全瞬间”演示：用非法 `request_id`（如 `bad.id`、`CON`）演示 HTTP 400；
   说明 `execute_pending_action` 非 APPROVED 抛 `PermissionError`，且 v0 无外部副作用。

## 3. 架构权衡（tradeoffs，诚实讲）

- **确定性先行**：先做可验证的规则基线，再接 LLM；避免“框架替你抽象了什么”说不清。
- **固定 plan vs 动态计划**：固定 plan 简单可测，但让 `tool_selection_accuracy` 恒 1.0 失去区分度；
  接 LLM 后改为模型选工具，需重建该指标的区分度。
- **linear orchestration vs explicit state machine vs LangGraph**：当前只有 typed state + 线性编排；P0 先把合法迁移显式化，LangGraph 仍只是条件化迁移（见 §7）。
- **关键词检索 vs 向量**：关键词检索无嵌入依赖、可复现，但召回有限；向量是可选增强，非 v0 目标。
- **内存审批 vs 持久化审批**：内存审批简单，但重启即丢、无认证、无终态；真实写前必须持久化 + 认证。
- **trace vs 审计**：trace 是运行线索，不是审计；明确不拿它当合规证据。

## 4. 深度问题强答（likely deep questions）

- **Q：为什么 top-k = 1.0？** A：因为生成逻辑与分类逻辑同源（同一套失效模式关键词/信号），
  这是循环验证，只证明自洽，不证明泛化；已计划 held-out 集来破环。
- **Q：evidence_recall 为什么只有 0.3698？** A：主因是 gold 相关证据含 EV-* 事件 id，而系统没有 events
  工具，事件证据永远无法召回；其次 WO 只看近 30 天（days=30）、limit=20、executor 只取前 10 条，大量 gold
  WO id 被窗口/截断漏掉。检索 DOCUMENT 证据不增加 recall（recall 只取 gold 交集）。补 events/维护工具可提升，
  证据使用率指标单独暴露“检索到却没用于推理”的装饰性 RAG 缺陷。
- **Q：safety_gate_compliance = 1.0 能说明安全吗？** A：不能。它只查提案停在 PENDING 门态，是
  静态代理指标；v0 无外部写所以恒真。执行级安全需接真实写后用新指标 + 审计 + 幂等 + 补偿重新证明。
- **Q：审批可信吗？** A：当前不可信——`approved_by` 硬编码、无认证、可逆、无终态、内存态跨进程不一致。
  这是接真实写前的 blocker，已列入 NEXT_PHASES 生产写 blocker。
- **Q：trace 能做审计吗？** A：不能。它记录调用/证据/假设/状态，但**不含** `approved_by`/`approved_at`/
  审批结果，且无 replay；审计需单独落库。
- **Q：工具 schema 生效吗？** A：schema 已声明（`ToolRegistry.schemas()`），但注册表 `call()` 不按 schema
  校验，边界约束靠工具内部 + `days/limit` 参数；这是已知 PARTIAL，需加固。
- **Q：怎么防 prompt injection？** A：当前确定性基线把 retrieved 文档当 data，不执行指令，且无 LLM
  故无指令跟随面；有 `prompt_injection` 场景覆盖。但这不是 LLM 集成后的防御证明，接 LLM 后要重做。
- **Q：为什么没接 LLM 却叫 agent？** A：架构按 LLM 可插拔设计（planner/synthesizer 是可替换件，
  工具 schema 已备好）；先做确定性基线是为了让评估、安全、观测这些“外围确定性系统”先可靠起来。

## 5. 失败案例（低 recall / 装饰性 RAG）

- **现象**：`docs/EVALUATION_REPORT.md` 显示 `evidence_recall = 0.3698`，但 `root_cause_top1 = 1.0`。
- **低 recall 根因**：gold `relevant_evidence_ids` 含 EV-* 事件 id（`ground_truth_failures.csv`），但系统
  没有 events 工具，事件证据永远无法召回；WO 查询 days=30/limit=20 且 `executor.py` 只取前 10 条，大量 gold
  WO id 因窗口/截断漏掉。这与检索质量无关，是“证据覆盖范围不足”。
- **装饰性 RAG（独立缺陷）**：`src/agent/executor.py` 把 `search_docs` 的 DOCUMENT chunk 追加进证据，但
  `src/agent/synthesizer.py` 的 `_rank()` 只消费 WO 文本 + meter 变化，DOCUMENT 证据对根因打分贡献为零；
  同时 `supporting_evidence_ids` 把全部证据无差别挂到非 normal 假设上（弱 claim grounding），meter 证据还
  用单一 `meter_summary:{asset_id}` 造成重复证据 id。这不是 recall 虚高，而是“检索到却没用于推理”。
- **教训**：recall 与 grounding 是两回事——recall 低暴露证据覆盖不足，装饰性 RAG 暴露证据使用不足；
  必须用“证据使用率/证据精度/根因证据覆盖”分别暴露，并用 held-out 集重新度量。
- **复述话术**：这是刻意保留的诚实失败点，用来展示“指标要分别看覆盖与使用，不能只看一个数字”。

## 6. 诚实指标口径（honest metrics explanation）

- 一句话：当前指标是 **合成数据上的回归自检**，不是能力或生产可用性声明。
- 明确区分：确定性 profile（可复现、硬阈值）vs 未来活体模型 profile（重复 N 次、mean±std、token/成本）。
- 明确各指标的循环/静态/代理性质，并给出替代公式（见 `docs/EVALUATION_METHODOLOGY.md` §5）。
- 报告归属：指标定义以 `EVALUATION_METHODOLOGY.md` 为准，代码/报告不得冲突。

## 7. 非目标防御（non-goal defenses）

- **LangGraph**：非目标。先用显式自有 runtime 把 state/retry/branching/persistence/observability/complexity
  自己讲清楚，再接 LLM，最后才评估是否迁移；否则分不清框架替你抽象了什么（NEXT_PHASES P2-1）。
- **长期记忆 / 会话历史**：非目标。当前 `AgentState` 是每次请求独立、ephemeral；无对话历史、无摘要、
  无长期记忆。加入前先论证“记住了什么、为什么需要、如何清理与脱敏”。
- **向量数据库 / embedding**：非目标。当前关键词检索足够演示；向量是可选增强，不是 v0 能力声明，
  也不会用“向量库存在”来抬高 RAG 成熟度。
- **真实 CMMS 写**：非目标，且是硬阻塞。v0 无外部写；在身份认证、审计、终态、多进程状态、幂等、
  trace 脱敏/保留、限流、回执/补偿、执行级安全全部验收前，审批结果不得触发任何外部写。

## 交叉引用

- 能力矩阵：`docs/CAPABILITY_MATRIX.md`
- 评估方法论：`docs/EVALUATION_METHODOLOGY.md`
- 安全威胁模型：`docs/SAFETY_AND_THREAT_MODEL.md`
- 评估数字：`docs/EVALUATION_REPORT.md`
- 后续计划：`docs/NEXT_PHASES.md`
- 系统手册：`docs/HANDBOOK.md`
