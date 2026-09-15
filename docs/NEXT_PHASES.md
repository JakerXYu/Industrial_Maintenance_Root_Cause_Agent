# 后续阶段路线图（P0 / P1 / P2）

> **本文是当前路线图与验收标准**，是“下一步做什么”的唯一事实来源。
> 文中所有条目均为**待实现项**，任何一条都不构成“已实现”声明；勾选状态一律以 `- [ ]` 表示未完成。
> 历史档案：`docs/WORKLOG.md`（总结日志）、`docs/WORKLOG_DETAILS.md`（详细日志）、`docs/PLAN_8H.md`（时间盒计划快照）。
> 当前能力与系统手册：`docs/CAPABILITY_MATRIX.md`、`docs/HANDBOOK.md`；Track A 报告见
> `docs/EVALUATION_REPORT.md`，已完成的 Track B 外部基准见
> `docs/EVALUATION_REPORT_EXTERNAL_HYDRAULIC.md` 与 `docs/benchmarks/HYDRAULIC_SYSTEMS_BENCHMARK.md`。

## 总原则

1. 每项在“完成”前必须同时具备：明确验收标准、自动化测试、可复现脚本或 CI 门禁；不满足验收即视为未完成。
2. 任何“真实 LLM / 真实写 / 向量检索”能力都不得成为默认依赖；必须有确定性兜底（fake provider、规则基线、keyword/FTS 检索）。
3. 每一步都要回答“怎么证明它做了，以及没做错”，落到指标而非主观判断。
4. Track B 已独立验证真实多传感器数据的摄取、特征、held-out 条件分类和 typed evidence；
   它不替代 P0-6 尚未完成的完整 Agent held-out 评估，也不得扩写成 RCA / 工单 / 文档能力。

## P0 — 可复现的工程基线与证据闭环（先于一切外部依赖）

> 编号用于主题引用，不代表实施依赖顺序。实际顺序是 `P0-1 → P0-3 → P0-2`：先建立
> runtime、schema enforcement、预算与调用账本，再接 live LLM。`P0-5/P0-6` 的证据闭环与
> 评估优先于或并行于 `P0-4`；BM25/FTS 只是可测检索 baseline，不能解决缺失 events 工具、
> WO 截断或“检索文档不参与推理”的问题。

### P0-1 受版本控制的基线、产物策略与 CI

- 建立可复现基线：固定合成数据生成脚本 + 依赖锁定（`requirements.txt` 或 lock + 版本 pin + hash）。
- 产物策略：源码、固定维修文档与精简评估报告进仓库；可再生的 `data/raw/*.csv`、`data/industrial.db`、本地 trace、索引、缓存、`.venv` 与真实密钥不进仓库。CI 临时生成数据和 DB 后运行测试，但不得上传 `ground_truth_failures.csv` 或 runtime trace 作为 artifact。
- CI：GitHub Actions（`.github/workflows/ci.yml`），步骤 `checkout → 装 Python → 装依赖 → 生成数据 → load DB → pytest → run_evaluation`。
- 验收：
  - [ ] 干净 clone 后一条命令从零复现数据、DB、测试与评估报告，无需任何手工步骤。
  - [ ] CI 门禁：`pytest` 全绿；评估硬指标相对基线不劣化（明确定义劣化阈值）；`ruff` lint 与 `black --check` 通过。
  - [ ] `ground_truth_failures.csv` 确认不入库、不进 Docker 镜像、不进 CI 缓存或 artifact。

### P0-2 有界可选真实 LLM + 确定性 fake / fallback

前置：先完成 P0-3 的 runtime 约束；本节复用其 schema validation、timeout/retry、step budget 与调用账本。

- 定义厂商无关的 `LLMProvider` 协议（`chat(messages, tools=None, response_model=None)`）。
- `FakeLLMProvider`：确定性、无网络、可注入固定响应与故障（超时 / 非法 JSON / 掉线），用于测试与 CI。
- 真实 provider：OpenAI 兼容客户端，走 `LLM_BASE_URL`；仅在显式配置 `LLM_API_KEY` 时启用，缺省走 fake。
- 有界性：每次请求的 token 上限、工具白名单（仅 `ToolRegistry.schemas()` 内已注册 read 工具）、输出 schema 校验。
- 落地位置：新增 `src/agent/llm.py`；替换 `src/agent/planner.py` 的 `interpret()/plan()` 与 `src/agent/synthesizer.py` 的 `synthesize()`。
- 验收：
  - [ ] 无 `LLM_API_KEY` 时全链路仍可跑（fake provider），CI 全程不联网。
  - [ ] 模型掉线 / 超时 / 返回非法 JSON 时按预定策略重试后优雅降级，不 crash，且记录到调用账本。
  - [ ] 模型只能选择白名单内 read 工具；任何写工具调用被拒绝。

### P0-3 显式 runtime + schema 强制 + 预算 + 独立 checkpoint / 调用账本

- 显式状态机：定义合法状态与合法迁移（`interpret → plan → execute → synthesize → done|error`；approve / reject 的终态语义），非法迁移抛错。
- schema enforcement：LLM 输出必须 `model_validate()` 通过，否则重试或降级。
- 预算：timeout、retry 上限、step 预算（每步工具调用次数上限）。
- 轻量独立 runtime SQLite（与业务 `industrial.db` 分离）：checkpoint（状态快照）+ invocation ledger（每次 LLM / 工具调用：谁、何时、入参、出参、耗时、token、状态）。
- 验收：
  - [ ] 非法状态迁移有测试断言抛错；终态后不可回退。
  - [ ] 超时 / 超预算 / 超重试场景有确定性测试，且 ledger 记录完整。
  - [ ] 重启后能从最近完成的 checkpoint 恢复，且不会重复执行账本中已成功的工具调用。
  - [ ] ledger 独立于业务 DB，仅追加、带唯一调用 id，可用于运行诊断；审批审计由 P1-2 单独实现。

### P0-4 Retriever 协议 + BM25 / FTS（先于 embeddings）

本项不是 decorative RAG 的单点修复。开始前先用 P0-5/P0-6 定义 evidence utilization、citation 与
held-out baseline；只有检索排序本身被证明是瓶颈时，BM25/FTS 的提升才算有效。

- 定义 `Retriever` 协议（`search(query, top_k) -> RetrievalResult`）。
- 先用 SQLite FTS5 或 BM25（`rank-bm25`）做全文检索，替换或增强现有 `KeywordRetriever`。
- 边界不变：结构化数据（库存 / 最新读数）走 SQL，手册 / SOP 走检索。
- 验收：
  - [ ] 所有检索实现同一协议、可互换；有 FTS/BM25 单测与检索质量微基准。
  - [ ] 检索结果带稳定唯一 chunk_id 与来源元数据，可溯源。

### P0-5 唯一证据 ID + claim 级 grounding / abstention

- 每条证据有全局唯一、稳定、可复现的 ID（如 `WO-0001`、`meter_summary:A001`、`doc_chunk:D123`）。
- 每个 `Hypothesis` 的每条 claim 必须映射到具体证据 ID（grounding）；证据不足时输出“证据不足 / abstain”，不编造 cause。
- 验收：
  - [ ] 每条 claim 可回溯到证据 id 列表；无证据时输出 abstain，有测试覆盖。
  - [ ] 证据 id 唯一性由契约与测试保证。

### P0-6 留出非循环评估（held-out，non-circular）

> 已完成的 Track B 解决了 diagnostic/evidence layer 的外部数据验证，但 UCI 数据没有工单、文档和
> Agent task ground truth，因此下面面向完整 Agent workflow 的 held-out 门禁仍是待办。

- 建立 held-out 评估集，与开发 / 调参所用场景隔离，避免“对着答案调参数”的循环。
- 指标覆盖：task success、tool selection precision / recall、tool argument 正确性、retrieval 命中、citation 正确性、unsupported-claim 检测、recovery、latency、token cost。
- 顺带补只读工具覆盖面（维护 / 备件 / 事件契约与工具），用于提升证据召回并纳入上述指标。
- 验收：
  - [ ] 评估脚本对 held-out 集可重复运行，输出全部指标到报告。
  - [ ] CI 门禁用 held-out 集判定不劣化；新增模型 / 检索 / 工具改动必须重跑。
  - [ ] 明确定义“劣化”阈值（相对基线的允许波动）。

## P1 — 安全与运维加固

### P1-1 在线 prompt-injection / 不可信输出安全

- retrieved 文档与用户输入一律当 data，不当指令；对不可信输出做 schema + 白名单校验；新增对抗用例。
- 验收：
  - [ ] prompt-injection 对抗集通过；LLM 无法借此绕过审批或改变工具白名单；输出失败时可回退到规则基线。

### P1-2 持久化 action proposal + 审计事件（不触达 CMMS）

- action proposal 与 approve / reject 审计事件落库（谁 / 何时 / 对哪个 action / 结果），但**不产生任何 CMMS 变更**。
- 验收：
  - [ ] approve / reject 事件可审计查询；仍无外部写；重启后审计记录仍在。

### P1-3 日志与运维容器验证

- 结构化日志（级别、request id 贯穿）；Historical base Docker Compose 曾完成 build/run/health。Current Track B 依赖镜像尚未重建验证，后续补 current smoke、CI 容器门禁和部署环境验证。
- 验收：
  - [x] Historical base 容器曾可构建、运行并通过 API / UI 健康检查。
  - [ ] Current Track B 依赖镜像 rebuild / health smoke（本次 daemon 不可用）。
  - [ ] CI 容器构建门禁、部署环境验证、结构化日志和 request id 贯穿追踪。

### P1-4 检索实验

- 在 Retriever 协议内比较 keyword / FTS / BM25 对 evidence recall 与 citation 的影响，出对比报告。
- 验收：
  - [ ] 有可复现对比脚本与报告，结论落到指标而非主观判断。

## P2 — 条件化增强

### P2-1 条件化 LangGraph

- 仅在 vanilla + 真实 LLM 稳定后评估迁移；写 `docs/VANILLA_VS_LANGGRAPH.md` 对比 state / retry / branching / persistence / observability / complexity。
- 验收：
  - [ ] 有对比文档与迁移决策记录；不满足“vanilla + 真实 LLM 稳定”前提则不迁移。

### P2-2 embeddings / hybrid / rerank

- 在 P0-4 检索协议之上插拔，作为可选后端；需在 held-out 集证明相对 BM25 有实际增益才采纳。
- 验收：
  - [ ] 有 held-out 对比报告，增益达标才纳入默认路径，否则仅保留实验分支。

### P2-3 多轮对话摘要

- 有限轮次上下文压缩，明确触发条件（何时压缩、保留哪些证据 id）。
- 验收：
  - [ ] 压缩后证据 id 与结论可回溯；有跨轮对话测试用例。

### P2-4 OpenTelemetry

- 结构化 trace / span / metrics 接入，与 P0-3 的 invocation ledger 对齐。
- 验收：
  - [ ] trace / span 可导出、可关联 request id；不重复记账。

### P2-5 沙箱 CMMS 适配器

- 在隔离沙箱内实现 CMMS 写适配器与执行回执 / 补偿，不触达真实 CMMS。
- 验收：
  - [ ] 沙箱内写 / 回执 / 补偿可测，且无任何真实 CMMS 变更。

## 非目标（除非触发条件满足）

- 长期记忆：除非多轮会话需要跨会话记忆，且先完成隐私 / 保留策略。
- 向量数据库：除非在 held-out 集证明 embedding + 向量检索显著优于 FTS/BM25 且成本可接受。
- 真实 CMMS 写：在“生产写 blocker”全部满足前，不产生任何真实 CMMS 变更。
- 多 agent：除非单一 agent 的复杂度与失败面被证明需要拆分。
- Kubernetes：除非出现多副本水平扩展、服务发现与自动扩缩的真实需求。

## 生产写 blocker（接真实 CMMS 写前的硬门槛，保持不变）

> 当前 v0 **没有**以下能力，仅是只读工具 + 内存审批门 + 不落外部写。在把 `ProposedAction`
> 接到真实 CMMS 写库之前，必须先补齐并验收以下每一项，缺一不可；在满足前，审批结果不得触发任何外部写。
> 这些项构成 P1-2 / P2-5 的验收前置；沙箱 CMMS 适配器只是不触达真实系统的前置演练。

- [ ] 身份认证 / 授权：API / UI 需认证，approve / reject 绑定真实操作者身份与权限，不能默认 `approved_by="operator"` / `"api"`。
- [ ] 持久化审批审计：approve / reject 落库（谁、何时、对哪个 action、结果）；当前内存审批重启即丢。
- [ ] 终态状态转移：审批需终态语义（APPROVED 后不可回 PENDING；REJECTED 的处理路径），当前只是内存字段拷贝。
- [ ] 多进程 / 多 worker 共享状态：当前 `pending` 是单进程内存 dict，多副本部署下状态不共享、不一致。
- [ ] 冲突 / 幂等：同一 action 的重复提交、并发审批、已执行后的重复执行需幂等与锁。
- [ ] trace 访问 / 脱敏 / 保留：trace 目前明文落盘，需访问控制、敏感字段脱敏、保留与清理策略。
- [ ] 请求限制 / 限流：对 `/agent/query`、审批、trace 读取做配额与限流，防滥用与 DoS。
- [ ] 执行回执 / 补偿：真实写操作需执行回执、失败补偿 / 回滚，写与审批之间不可静默丢失。
- [ ] 执行级安全评估：新增“真实写路径”的执行级安全校验，区别于当前 `safety_gate_compliance`（后者只是提案门态检查）。

## 新增依赖（计划，尚未引入）

| 用途 | 包 | 说明 |
|---|---|---|
| LLM client | `openai` | OpenAI 兼容，走 `base_url` |
| 检索（可选） | `rank-bm25` | 若 FTS5 不足再引入 |
| lint / format | `ruff`、`black` | 用于 CI 门禁 |
| parquet（可选） | `pyarrow` | 仅当切换 `meter_readings` 存储时引入 |
| 编排（可选） | `langgraph` | 仅 P2-1 条件满足时引入 |
| 可观测（可选） | `opentelemetry-api` / `opentelemetry-sdk` | 仅 P2-4 时引入 |

> 上表均为“计划”，当前尚未作为运行依赖引入；现有运行依赖（`pydantic`、`pandas`、`numpy`、`fastapi`、`uvicorn`、`streamlit`、`pytest`、`httpx`）见 `docs/HANDBOOK.md`。
