# 安全与威胁模型 SAFETY_AND_THREAT_MODEL

> 本文定义资产、信任边界、威胁角色、具体威胁、当前控制与明确的不保证（non-guarantees）、
> 未来控制与真实写路径前的 blocker。配套：`docs/CAPABILITY_MATRIX.md`、`docs/NEXT_PHASES.md`、
> `docs/EVALUATION_METHODOLOGY.md`。当前版本是确定性 baseline（未接 LLM），安全结论只对本版本成立。

## 1. 资产（assets）

| 资产 | 位置 | 价值 | 当前暴露 |
|---|---|---|---|
| 合成 CMMS 数据（assets/wo/meter/…） | `data/raw/`、`data/industrial.db` | 设备/工单/计量事实 | 只读工具可查 |
| 维修文档（SOP/手册） | `data/docs/*.md` | RAG 语料 | `search_docs` 可检索 |
| ground-truth 标注 | `data/raw/ground_truth_failures.csv` | 评估答案 | 不入库、不进镜像、运行时不可读 |
| 审批状态 `ProposedAction` | 进程内存（`src/api/main.py` `pending` / Streamlit `st.session_state`） | 写动作门禁 | 进程内/会话内可读写 |
| trace | `traces/*.json` | 可观测性/诊断记录（非审计） | 明文落盘，可读 |
| 密钥 `LLM_API_KEY` | 环境变量 → `src/config.py` `SecretStr` | 外部模型凭证 | repr 隐藏，`.env` 不入库 |

## 2. 信任边界（trust boundaries）

- **入口 → 契约**：外部问题文本、`request_id`、query 参数进入系统，均视为不可信。
- **契约 → 数据层**：只读 SQLite（`mode=ro`）是最后一道数据面；写必须经审批门，且 v0 无任何外部写。
- **进程 → 外部**：当前无外部写目标（无 CMMS、无真实 DB 变更）；这是“无副作用”的信任边界，也是当前最大的安全简化。
- **文件系统**：`trace` 落盘是唯一写文件路径，受 `request_id` 校验 + 路径包含约束。

## 3. 威胁角色（threat actors）

- **终端用户**：通过 UI/API 提交问题或点审批，可能是误操作或恶意。
- **提示注入者**：在问题文本或文档语料中夹带指令，试图改变 agent 行为。
- **内部误用者**：可访问内存审批表或 trace 的运维者。
- **外部网络攻击者**：扫描 API、刷接口、构造非法 `request_id`/路径穿越、探测密钥。

## 4. 威胁 → 当前控制 → 非保证

| 威胁 | 当前控制（代码证据） | 明确不保证（non-guarantee） |
|---|---|---|
| 提示注入（prompt injection） | 有 `prompt_injection` 场景（`src/evaluation/scenarios.py`）；确定性基线把 retrieved 文档当 data，不执行文档指令；无 LLM 故无指令跟随面 | 不是 LLM 集成后的注入防御证明；文档当 data 的前提在接 LLM 后需重新验证 |
| 不可信输出 / 工具滥用 | 只暴露 4 个只读工具（`src/agent/tools.py`）；plan 固定（`planner.py`）不可由输入改写 | 接 LLM 后模型自由选工具时，此“固定 plan”防线失效，需重做约束（NEXT_PHASES P0-2） |
| 路径穿越 / 非法 request_id | `^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$` + Windows 保留名拒绝 + trace 路径包含，三处强制（`src/agent/request_id.py`，API/runner/TraceStore） | 只覆盖 request_id 触达的 trace 文件名；其他任何以用户输入构路径的场景未覆盖 |
| 审批被绕过 | `execute_pending_action` 非 APPROVED 抛 `PermissionError`（`src/agent/policy.py`） | 审批本身无认证：`approved_by` 硬编码 `"api"`/`"operator"`；任何能调到 approve 端点者都可审批 |
| 审批可逆 / 无终态 | 无 | `approve`/`reject` 只是 `model_copy` 字段改写，APPROVED 后可再 REJECT，无终态/幂等/锁 |
| 审计缺失 | trace 是可观测性/诊断记录，记录调用/证据/假设/状态（`src/agent/tracing.py`） | trace **不是**审计：不含 `approved_by`/`approved_at`/审批结果，无 replay，不能作为合规证据 |
| 密钥泄漏 | `SecretStr` repr 隐藏；`.env` 不入库（`.gitignore`） | 环境变量本身不加密；未来结构化应用日志若错误打印 config 仍可能泄露，当前尚无该日志层 |
| DoS / 资源滥用 | 无 | 无限流、无配额、无请求体大小限制；`/agent/query`、trace 读取、审批均可被刷 |
| 数据面越权写 | 只读连接 + 无写工具 + `execute_pending_action` 无副作用 | 是“无外部写”带来的静态安全，不是写路径的访问控制；接真实写后必须重做 |
| 状态跨进程不一致 | 无 | `pending` 是单进程内存 dict，多 worker 部署下审批状态不共享、不一致 |

## 5. 未来控制（接真实写之前的硬 blocker，见 NEXT_PHASES 生产写 blocker）

以下每一项在把 `ProposedAction` 接到真实 CMMS 写库前必须补齐并验收，缺一不可：

- 身份认证 / 授权：API/UI 认证，approve/reject 绑定真实操作者与权限。
- 持久化审批审计：谁、何时、对哪个 action、结果，落库。
- 终态状态转移：APPROVED 后不可回 PENDING；REJECTED 有处理路径。
- 多进程共享状态：替换内存 dict。
- 冲突 / 幂等：重复提交、并发审批、重复执行。
- trace 访问控制 / 脱敏 / 保留清理。
- 请求限制 / 限流。
- 执行回执 / 补偿 / 回滚。
- 执行级安全评估：替代 `safety_gate_compliance` 这一门态代理指标。

## 6. 真实写路径 blocker 的判定

- **当前状态**：`execute_pending_action` 只返回 APPROVED 的 action，不产生任何 CMMS 变更（`policy.py` 注释明确）。
- **判定规则**：只要 §5 任何一项未验收，审批结果就不得触发外部写；这是硬阻塞，不因演示需要而豁免。
- **写路径上线门槛**：新增“真实写路径”执行级测试 + 审计 + 限流 + 幂等 + 补偿全绿，并替换安全门禁指标后，才允许引入外部副作用。

## 交叉引用

- 能力状态：`docs/CAPABILITY_MATRIX.md`
- 评估安全指标局限：`docs/EVALUATION_METHODOLOGY.md`
- 后续 blocker 与落地：`docs/NEXT_PHASES.md`
- 系统安全实现细节：`docs/HANDBOOK.md` §19
- 面试答辩口径：`docs/INTERVIEW_GUIDE.md`
