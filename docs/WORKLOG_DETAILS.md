# Worklog（详细版·历史记录）

> **本文是历史记录**：逐阶段、逐文件记录那一轮开发每一步做了什么、为什么这么做、踩了什么坑、
> 怎么修的、怎么验证的。它是 `docs/WORKLOG.md`（总结版）的展开，二者同属历史档案；
> 文中的“已实现 / 全绿”均为当时状态，**不作为当前能力声明**。
> 当前状态以 `docs/NEXT_PHASES.md`（路线图）、`docs/CAPABILITY_MATRIX.md`（能力矩阵）为准；
> 系统手册见 `docs/HANDBOOK.md`，时间盒计划快照见 `docs/PLAN_8H.md`，评估报告见 `docs/EVALUATION_REPORT.md`。

## 环境与依赖

- OS：Windows
- Python：3.9.13（Anaconda base），项目用独立 `.venv`
- 安装的依赖（按阶段）：`pydantic`、`pytest` → `pandas`、`numpy` → `fastapi`、`uvicorn`、`httpx`、`streamlit`
- 附带被 streamlit 拉进来的：`pyarrow` 等

网络在沙箱里受限，`pip install` 需要提权执行；本会话中分三次安装依赖，均已通过。

## 阶段 0：脚手架与契约（Phase 0）

### 做了什么

- 建立目录：`src/contracts`、`src/tools`、`scripts`、`data`、`tests`、`traces`。
- 写入第一批文件：`README.md`、`.env.example`、`requirements.txt`、`src/config.py`、`src/contracts/*`、`tests/test_contracts.py`。
- 定义契约：`Asset`、`WorkOrder`、`MeterReading`、`MeterSummary`、`EvidenceItem`、`ToolError`、`ToolResult`、`ProposedAction`。

### 关键决策

- `ToolResult` 是统一信封，用 `empty`（成功但 0 行）与 `error`（真失败）区分，这是后面工具层的核心语义。
- `ProposedAction` 默认 `PENDING_APPROVAL`，把“write 不可自动执行”写进数据模型，而不是靠运行时口头约定。
- `ProposedAction` 放在 `common.py`：它同时被 agent 与 policy 层使用，属于跨层契约；当时文件清单没有单独的 `actions.py`。
- 补了必要的 `__init__.py`、`.gitignore`、`.gitkeep`（脚手架，不是逻辑文件）。
- `requirements.txt` 只放当前真正需要的包，未来依赖写在注释里。
- `src/config.py` 用 `SecretStr` 存 API key，`repr` 不泄露密钥。

### 遇到的问题与修复

- `pip install -r requirements.txt` 报 `UnicodeDecodeError: 'gbk' codec can't decode byte 0x94`：`requirements.txt` 注释里的 em-dash（`—`）在中文 Windows 的 GBK 环境下被 pip 误读。修复：把注释改成纯 ASCII。
- 之后 pip 报 `WinError 10013`：沙箱拦截网络。修复：提权执行安装。

### 验证

`tests/test_contracts.py`：11 个用例，覆盖校验、枚举序列化、JSON 往返、`ToolResult` 三种状态、`ProposedAction` 状态迁移、`Settings` 密钥隐藏。首次全绿。

## 阶段 1：模拟数据（Synthetic data）

### 做了什么

- 写 `scripts/generate_synthetic_data.py`，输出 10 个 CSV 到 `data/raw/`，5 篇虚构 Markdown 到 `data/docs/`。
- 规模：25 资产、180 天、2 小时采样（54000+ 读数）、285-310 工单、100 零件、12 task groups。
- 6 种失效模式，注入到固定资产：
  - `A001` hydraulic_press → lubrication_degradation（温度↑ + 振动微↑）
  - `A006` robotic_welding_cell → position_sensor_instability（振动毛刺）
  - `A011` cnc_machine → bearing_degradation（振动↑ + 温度↑）
  - `A015` cnc_machine → cooling_degradation（温度↑）
  - `A016` industrial_pump → hydraulic_leakage（压力↓）
  - `A025` hydraulic_press → normal_or_false_alarm（孤立毛刺 + 误导工单）
- 数据瑕疵：~1.5% 缺失、24 条重复读数、误导性工单、延迟完工。
- `ground_truth_failures.csv` 只用于评估，不进 DB、不暴露给 agent。
- 写 `tests/test_synthetic_data.py`。

### 关键决策

- 固定 seed，脚本幂等（覆盖写），保证可复现。
- 失效信号注入到“最近窗口”（day 150-162 之后），保证 baseline-vs-recent 有真实差异。
- v1 用 CSV 而非 parquet，避免额外 pyarrow 依赖（后来 streamlit 顺带装了 pyarrow，但没回头改）。

### 遇到的问题与修复

- `_make_maintenance_plans` 里 overdue 判断写成了无意义的 `"lubricat" in f"plan{plan_id}"`，导致 overdue 逻辑从未触发。修复：改成 `p == 0 and mode in OVERDUE_DAYS`，并显式算 `next_due = SIM_END - overdue_days`。
- 最初失效开始日设在 day 115-135，导致“30 天基线 vs 最近 7 天”两个窗口都落在失效期内，指标看不出异常。修复：把开始日推迟到 day 150-162。

### 验证

`tests/test_synthetic_data.py`：9 个用例。PK 唯一、FK 有效、非负 cycle_count、时间窗、缺失值存在、重复行存在、注入信号模式（A001 温度↑ / A016 压力↓ / A011 振动↑ / A015 温度↑）。全绿。

## 阶段 2：SQLite 数据层（Phase 1 上半）

### 做了什么

- `src/db/schema.py`：9 张表的 DDL。
- `scripts/load_database.py`：读 CSV、建表、`executemany` 入库。
- `src/db/repository.py`：只读 `Repository`。
- `tests/test_repository.py`。

### 关键决策

- 用标准库 `sqlite3` + 参数化 SQL，而不是 SQLAlchemy：Pydantic 已经是输出契约，ORM 是多余抽象。
- repository 用 `mode=ro` 只读连接；`get_asset` 返回 `Optional[Asset]`，查不到是 `None` 而不是异常。
- “最近 N 天”以表内 `MAX(timestamp/created_at)` 为基准，避免合成数据因“现在”晚于数据导致查空。
- `WorkOrder`/`MeterReading`/`Asset` 直接从 `dict(row)` 用 Pydantic 强转，日期字符串、枚举字符串都由 Pydantic 统一 coerce。

### 遇到的问题与修复

- 直接跑 `python scripts/load_database.py` 报 `ModuleNotFoundError: No module named 'src'`，因为脚本入口的 `sys.path[0]` 是 `scripts/`。修复：脚本顶部加 `sys.path.insert(0, str(ROOT))`。

### 验证

`tests/test_repository.py`：4 个用例（资产命中/未命中、list 排序、近期工单、近期读数）。全绿。

## 阶段 3：只读工具（Phase 1 下半）

### 做了什么

- `src/tools/asset_tools.py`、`work_order_tools.py`、`meter_tools.py`。
- `tests/test_tools.py`。

### 关键决策

- 每个工具返回 `ToolResult`；参数非法 → `INVALID_ARGUMENT`；上游/DB 失败 → `UPSTREAM_UNAVAILABLE`；查不到 → `empty=True`。
- 工具层是“空结果 vs 错误”语义的实际体现点。

### 遇到的问题与修复

- 测试里 `get_meter_history_tool(..., limit=100000)` 超过工具上限 10000，被判定为 `INVALID_ARGUMENT`。修复：测试改用 10000。

### 验证

`tests/test_tools.py`：4 个用例（asset 成功/空/非法、list、工单搜索、meter 成功/空/非法）。全绿。

## 阶段 4：确定性分析（Phase 2）

### 做了什么

- `src/analytics/trend.py`：`compute_meter_summary`（baseline 30d vs recent 7d + 斜率）。
- `src/analytics/anomaly.py`：MAD、modified z-score、rolling z-score、`flag_anomalies`。
- `tests/test_analytics.py`。

### 关键决策

- 数值结论（基线对比、相对变化、斜率、异常）全由代码算，LLM 不读原始行。
- `relative_change_pct = (recent - baseline) / baseline * 100`；斜率用 `numpy.polyfit` 对时间戳做最小二乘。

### 遇到的问题与修复

- `SignalSummary.baseline_mean/recent_mean` 是必填 float，某信号全缺失时会传 None 导致校验失败。修复：`_signal_stats` 在均值缺失时返回 None，`compute_meter_summary` 跳过该信号。

### 验证

`tests/test_analytics.py`：3 个用例（lubrication 温度上升、hydraulic 压力下降、modified z-score 检出 spike）。全绿。

## 阶段 5：RAG v0（Phase 3）

### 做了什么

- `src/contracts/rag.py`：`DocumentChunk`、`RetrievalResult`。
- `src/rag/chunking.py`：heading-aware 分块 + `load_documents`。
- `src/rag/retriever.py`：`KeywordRetriever`（倒排索引 + 词重叠打分）。
- `tests/test_rag.py`。

### 关键决策

- 分块按 Markdown 标题切 section，section 内超长再按 `target_chars` 滑动窗口切，带 `overlap_chars` 重叠；`chunk_id` 稳定（`document:NNN`）。
- v0 用关键词检索，零 embedding 依赖；embeddings 是可替换后端。
- 当前库存 / 最新读数走 SQL，手册 / SOP 走 RAG，边界明确。

### 遇到的问题与修复

- 测试里写了丑陋的 `__import__("pathlib").Path(...)`。修复：正常 `from pathlib import Path` 并用绝对路径。

### 验证

`tests/test_rag.py`：3 个用例（分块 section 识别、加载 5 篇文档、检索命中正确 chunk）。全绿。

## 阶段 6：Vanilla Agent 状态机（Phase 4）

### 做了什么

- `src/contracts/agent.py`：`Hypothesis`、`AgentStatus`、`ToolCallTrace`、`TraceRecord`、`AgentState`。
- `src/agent/tools.py`（ToolRegistry + JSON schema）、`planner.py`、`executor.py`、`synthesizer.py`、`policy.py`、`tracing.py`、`runner.py`。
- `tests/test_agent.py`。

### 关键决策

- 流程：`interpret → plan → execute → synthesize → trace`。
- `interpret` 用正则 `\bA\d{3}\b` 解析资产；解析不到或查不到 → `ERROR`。
- `plan` 是确定性的 4 步：get_asset、search_recent_work_orders、get_meter_history、search_docs。
- `executor` 记录每次工具调用的 `ToolCallTrace`（工具名、参数、状态、结果数、延迟），并把结果转成 `EvidenceItem`。
- `synthesizer` 计算 meter summary，把 WO 症状文本 + 信号变化喂给规则分类器，产出 `Hypothesis`（带 evidence id）。
- `runner` 捕获异常，优雅降级为 `ERROR`，不 crash harness。

### 遇到的问题与修复

- “missing asset”测试用 `Z999`，但正则只认 `A\d{3}`，走到了“无法解析”分支而非“资产不存在”分支。修复：改用 `A999`，命中“不存在”路径，断言也改为“No asset”。

### 验证

`tests/test_agent.py`：8 个用例（4 种失效模式、normal、missing asset、审批门阻断、trace 往返、prompt injection 当 data）。全绿。

## 阶段 7：证据假设与审批门（Phase 5-7）

### 做了什么

- `ToolRegistry.schemas()` 对齐 OpenAI function-calling 格式。
- `synthesizer` 的规则分类器（`MODE_KEYWORDS` + 信号 boost）。
- `policy.approve/reject/execute_pending_action`。

### 关键决策

- 分类是确定性启发式（baseline），后续接 LLM 时只替换 `planner` / `synthesizer`。
- `execute_pending_action` 在非 `APPROVED` 状态直接 `raise PermissionError`，用测试证明“未审批不可执行”。
- `Hypothesis` 必须带 `supporting_evidence_ids` / `contradicting_evidence_ids`，区分事实、检索指导、推断。

### 验证

- 审批门阻断用 `pytest.raises(PermissionError)` 验证。
- prompt injection 用例：问题里塞“ignore all previous instructions”，agent 仍按证据返回 lubrication，未执行任何写操作。

## 阶段 8：Trace / 离线评估（Phase 8-9）

### 做了什么

- `src/agent/tracing.py`：`TraceStore`（JSON 落盘）+ `to_trace_record`。
- `src/evaluation/scenarios.py`（30 场景）、`metrics.py`（7 项质量指标，另含场景总数）、`runner.py`（跑评估 + 写报告）。
- `scripts/run_evaluation.py`。
- `tests/test_evaluation.py`。

### 关键决策

- 每次请求按 `request_id` 落一条 JSON trace，可加载和检查；当前没有重新执行历史请求的 replay 引擎。
- 评估只算可机检硬指标，不写“看起来不错”的软结论。

### 遇到的问题与修复

- 首跑 `tool_selection_accuracy = 0.9655`：missing_asset 场景 `required_tools=["get_asset"]`，但资产解析是 `interpret` 里的直接查询，不是计划内工具调用。修复：missing_asset 的 `required_tools=[]`（解析到“不存在”即正确停止），指标回到 1.0。

### 验证

- `tests/test_evaluation.py`：2 个用例（场景数 ≥30、端到端 top1/safety/recovery = 1.0）。
- 最终 30 场景指标：root-cause top-1/top-3 = 1.0，asset resolution = 1.0，tool selection = 1.0，safety = 1.0，recovery = 1.0，evidence recall = 0.3698。
  > 历史口径提醒：上表 1.0 均为合成数据 + 规则基线结果；`recovery = 1.0` 仅表示错误/对抗场景能优雅降级为 `ERROR`，不构成故障恢复/重放/补偿能力；`evidence recall = 0.3698` 反映当时关键词检索 + 有限工具覆盖，不等于“证据可支撑的 RAG”；`safety = 1.0` 只是提案门态静态检查，不是生产安全证明。

## 阶段 9：API / UI / Docker（Phase 11-14）

### 做了什么

- `src/api/main.py`：FastAPI，8 个端点。
- `ui/streamlit_app.py`：Agent / Asset Explorer / Trace Inspector 三个 tab。
- `Dockerfile`、`.dockerignore`、`docker-compose.yml`。
- `tests/test_api.py`、`tests/test_streamlit.py`。
- 安装 `fastapi`、`uvicorn`、`httpx`、`streamlit`。

### 关键决策

- API 复用现有 `Repository` + `AgentRunner`；UI 与逻辑解耦（Streamlit 先走进程内，后续可切 HTTP API）。
- 审批走 `/actions/{action_id}/approve|reject`，`action_id` 就是 `/agent/query` 返回的 `request_id`。
- Docker 构建时重新生成数据，并 `rm -f data/raw/ground_truth_failures.csv`，保证评估专用文件不进镜像（此为 `Dockerfile` 的设计意图，**未在真实 Docker 环境构建/运行验证**）。

### 验证

- `tests/test_api.py`：4 个用例（health、asset/work-orders、meter-summary、query+approve+trace 全流程）。
- `tests/test_streamlit.py`：1 个 `AppTest` 无头冒烟用例。
- Docker 镜像构建与运行：**未验证**（仅提交文件）。
- 全量测试 **49 passed**（此时点；后续收口到 66，见阶段 10）。

## 阶段 10：Post-review Security and Contract Hardening

### 做了什么

对全链路做了一次安全与契约复核，修复了 request id 作为路径基名、审批审计元数据、指标口径、空输入语义和文档过度声明等问题，并把测试从 49 收口到 66。

### 问题与修复

1. **request id 无校验即当文件名**：request id 直接拼成 trace 文件名，`../`、空格、`.`、`CON`/`NUL` 等都可能造成路径穿越或 Windows 保留设备名非法文件。
   - 修复：新增 `src/agent/request_id.py`，统一校验 `^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$`，并拒绝 `CON`/`PRN`/`AUX`/`NUL`/`COM1-9`/`LPT1-9`；`request_id_path` 做 resolve + 包含性检查。
   - 三个边界强制：`AgentRunner.run`、FastAPI 路由、`TraceStore.save/load`；非法 ID 抛 `InvalidRequestIdError`（API 转 HTTP 400）。
2. **审批时间元数据未进入状态迁移**：原流程会记录 `approved_by`，但 approve 不填 `approved_at`，reject 也不会主动清除可能残留的批准时间。
   - 修复：`policy.approve_action` 写入 `approved_by` 与时区感知 `approved_at`（UTC）；`policy.reject_action` 写入 `approved_by` 并把 `approved_at` 清空为 `None`。
3. **`asset_resolution_accuracy` 分母口径错误**：把 `expected_asset_id is None` 的场景（missing / ambiguous）也算入分母，`None == None` 会被当成解析正确，指标可能虚高、语义被误导。
   - 修复：`metrics.compute_metrics` 只统计 `expected_asset_id is not None` 的场景对。
4. **空分析输入语义未定义**：无读数时走空 DataFrame 路径，行为不稳定。
   - 修复：`compute_meter_summary` 对空输入返回带类型 `MeterSummary`（`signals={}`，`baseline_days` 来自请求，`recent_days` 保持固定 7 天窗口）。
5. **文档过度声明**：把 trace 的保存 / 加载称为 replay、把审批决策说成可追溯，并把 `safety_gate_compliance` 说成执行证明。
   - 修复：在 `HANDBOOK.md` / `WORKLOG.md` 明确当前只有 trace 持久化与检查，没有 replay 引擎或审批事件持久化；safety 指标定性为“提案门态符合”的静态检查。

### 关键决策

- request id 校验集中到 `request_id.py`，避免 API / runner / trace 三处各自实现产生不一致。
- 审批仍是内存态、无外部动作；本次只是把审计字段与边界语义写对，不引入持久化（持久化属于生产硬阻塞项，见 `NEXT_PHASES.md`）。
- UI 审批决策明确为 `st.session_state` 会话内状态，文案声明“v0 不执行外部动作”。

### 验证

- 新增 `tests/test_request_id.py`（7 个）：合法 / 非法字符集与长度、Windows 保留名、路径包含、trace 存储拒绝、runner 拒绝空 ID。
- 新增 `tests/test_agent.py` 4 个：审批时间戳时区感知、reject 清空 `approved_at`、reject 覆盖旧审批、无 action 时 `execute_pending_action` 返回 None。
- 新增 `tests/test_analytics.py` 2 个：空输入返回带类型 summary、窗口值传播。
- 新增 `tests/test_evaluation.py` 1 个：分母排除 None 期望资产。
- 新增 `tests/test_api.py` 3 个：`/agent/query` 拒绝非法 ID、trace/actions 路由拒绝保留名。
- 全量 `pytest`：**66 passed**。

### 延后（生产项，非本次范围）

身份认证 / 授权、持久化审批审计、终态状态转移、多进程共享状态、冲突 / 幂等、trace 访问 / 脱敏 / 保留、请求限制 / 限流、执行回执 / 补偿、执行级安全评估——这些是真实 CMMS 写操作前的硬阻塞项，v0 不含。

## 历史阶段-10 测试分布快照（Historical Phase-10 Snapshot）

> 下表是阶段 10（Post-review Security and Contract Hardening）收尾时的测试分布快照，
> 当时合计 **66 passed**。它**不是**当前分布；当前分布见下方「测试用例演进时间线」。

| 文件 | 用例数 |
|---|---|
| test_contracts.py | 11 |
| test_synthetic_data.py | 9 |
| test_repository.py | 4 |
| test_tools.py | 4 |
| test_analytics.py | 5 |
| test_rag.py | 3 |
| test_agent.py | 12 |
| test_evaluation.py | 3 |
| test_api.py | 7 |
| test_streamlit.py | 1 |
| test_request_id.py | 7 |
| 合计 | 66 |

## 测试用例演进时间线（Test-count Chronology）

| 里程碑 | 合计 | 相对上一里程碑的增量 |
|---|---|---|
| 历史阶段-10 快照 | 66 | —（上表，历史分布） |
| pre-Track-B | 71 | +5 = API +1（`test_api.py` 7→8）+ UI +4（`test_streamlit.py` 1→5） |
| 当前（含 Track B） | 114 | +43 = Track B（`test_hydraulic_benchmark.py` 26 + `test_diagnostic_evidence.py` 17） |

> pre-Track-B 的 71 是引入 Track B 之前的测试基线（与 `docs/benchmarks/HYDRAULIC_SYSTEMS_BENCHMARK.md`
> 的「本轮前 71 passed」一致）；当前 114 为加入 Track B core 与 evidence/integration 测试后的总数。
> Track A 的 30 场景与原指标保持不变。

## 尚未实现（历史遗留项，现由路线图承接）

- 接真实 LLM（替换 planner/synthesizer）
- 维护/备件/事件契约与工具
- `meter_readings` 切 parquet
- CI（GitHub Actions + 评估门禁）
- 可选 LangGraph 迁移

以上已并入 `docs/NEXT_PHASES.md` 的 P0 / P1 / P2 路线图；本文不再作为当前能力或计划来源。
