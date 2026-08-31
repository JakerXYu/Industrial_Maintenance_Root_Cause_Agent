# 能力矩阵 Capability Matrix

> 逐项对照当前实现事实，每项一个独立行，标注状态、证据路径与目标处置。状态语义：
> `IMPLEMENTED`=已实现并有测试/代码证据；`PARTIAL`=已实现但存在缺陷、边界或仅为隐式/代理；
> `MISSING`=当前完全不存在；`OUT OF SCOPE`=仅用于明确记录为「刻意非目标」的项（如长期记忆、
> 真实写、向量 DB），并给出准确限定；其余缺失的核心目标一律记为 `MISSING`。
> 处置：`保持`=维持现状；`加固`=补齐约束/测试/真实语义；`新增`=后续实现；`延后`=条件满足才做。

事实基线：确定性 baseline（未接 LLM）；固定 plan；只读工具；SQLite；71 测试；30 场景；
评估为 **7 项指标 + `total_scenarios` 计数**（不是 8 项指标）。
来源：`../README.md`、`docs/HANDBOOK.md`、`docs/NEXT_PHASES.md`（P0/P1/P2 路线图）、`docs/EVALUATION_REPORT.md`。

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
| Reproducible test cases（可复现用例） | IMPLEMENTED | 固定 seed 生成 + 71 测试 + 30 场景 | 保持 |
| Unit / integration / eval tests（单测 / 集成 / 评估） | IMPLEMENTED | `tests/` 71 用例跨层 + `src/evaluation/` 离线评估 | 保持 |
| Docker | IMPLEMENTED | 本地 Compose 已真实 build/recreate；API 8001→8000 healthy，UI 8502 health 200 | 生产部署与 CI gate 仍属后续 |
| API | IMPLEMENTED | `src/api/main.py`（FastAPI） | 保持 |
| CLI or UI（命令行或界面） | IMPLEMENTED | `ui/streamlit_app.py`（Streamlit）；无 CLI | 保持 |

## 交叉引用

- 系统实现细节：`docs/HANDBOOK.md`
- P0/P1/P2 路线图与非目标：`docs/NEXT_PHASES.md`
- 评估结果：`docs/EVALUATION_REPORT.md`
- 指标定义与局限：`docs/EVALUATION_METHODOLOGY.md`
- 安全威胁建模：`docs/SAFETY_AND_THREAT_MODEL.md`
- 面试答辩：`docs/INTERVIEW_GUIDE.md`
