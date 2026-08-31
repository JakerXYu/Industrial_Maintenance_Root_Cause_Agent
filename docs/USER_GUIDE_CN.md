# 用户指南（中文）— 工业维护根因分析 Agent

> 本文面向**第一次使用本项目的用户**：讲清「这是什么、怎么装、数据在哪、页面怎么用、
> 怎么验证、出问题怎么排」。不重复架构细节——实现参考看 [HANDBOOK.md](HANDBOOK.md)，
> 指标口径与局限看 [EVALUATION_METHODOLOGY.md](EVALUATION_METHODOLOGY.md)，
> 安全边界看 [SAFETY_AND_THREAT_MODEL.md](SAFETY_AND_THREAT_MODEL.md)。

---

## 0. 30 秒：这是什么、不是什么

**是什么**：一条可复现、可测试的**确定性**工业维护根因分析管线。输入一句问题（例如
`A001 stopped this week`），系统用只读工具查询设备、工单、仪表趋势与维修文档，输出
根因假设（hypothesis）、证据（evidence）、建议核查步骤（recommended_checks）与一个**待审批**的
动作（pending action）。

**请先知道的五件事**（面试与使用时都不要误读）：

1. **确定性、无 LLM**。当前解释器 / 规划器 / 综合器全部是规则代码，不调用任何语言模型。
   `LLM_*` 配置项只是为未来预留，当前不读取、不使用。
2. **文档检索只是 scaffold**。检索是 token-overlap 关键词匹配（非 BM25、非向量、非混合），
   且检索到的文档**不参与**根因打分，只被「引用」。
3. **没有真实写操作**。写类动作只产出 `ProposedAction`，初始状态恒为 `PENDING_APPROVAL`；
   批准/拒绝只改内存里的状态，**不会**真的改任何 CMMS / 数据库 / 外部系统。
4. **trace 不是审计 / 检查点 / 记忆**。`traces/*.json` 是运行结束后的**只读快照**，
   可查看、不可重放、不可恢复；没有跨请求记忆，没有 checkpoint / resume。
5. **ground truth 只用于评估**。`ground_truth_failures.csv` 不入库、不进镜像、**绝不**
   暴露给 Agent 或 UI，运行时不可见。

**非保证（边界，勿过度声明）**：不是生产系统；无认证 / 授权、无结构化应用日志、无 CI、
无限流、无执行回执；审批是**进程内 / 会话内内存态**，重启即丢、多进程不共享。

---

## 1. 前置条件与首次安装

### 1.1 前置条件

| 项目 | 要求 |
|---|---|
| Python | 3.10 / 3.11（Dockerfile 使用 `python:3.11-slim`） |
| 包管理 | `pip`（随 Python 自带） |
| 操作系统 | Windows（本文命令为 PowerShell 5.1） |
| Git | 可选，用于克隆仓库 |
| Docker | 可选；见下文「4.3 Docker」的诚实状态说明 |

### 1.2 首次安装（PowerShell，在项目根目录执行）

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt
```

验证安装：

```powershell
.\.venv\Scripts\python -c "import fastapi, streamlit, pydantic; print('ok')"
```

> 本文所有命令都使用 `.\.venv\Scripts\python` 前缀，从**项目根目录**运行。

---

## 2. 数据生命周期（generate → load → test → evaluate → run）

完整的开发验证链路包含下面五步；第一次只想看页面时，最短路径是“生成 → 入库 → 运行”，
`pytest` 与离线评估属于可选验证步骤。图示：

```text
scripts/generate_synthetic_data.py     生成可复现数据
        │  → data/raw/*.csv（10 个）+ data/docs/*.md（5 篇虚构文档）
        ▼
scripts/load_database.py               入库
        │  → data/industrial.db（SQLite，只读打开）
        ▼
python -m pytest                       自检
        │  → 71 个用例全绿
        ▼
scripts/run_evaluation.py              离线评估
        │  → 30 场景 → docs/EVALUATION_REPORT.md + traces/eval-*.json
        ▼
uvicorn / streamlit run                运行（API / UI）
           → 每次请求落一份 traces/<request_id>.json
```

对应的完整命令：

```powershell
.\.venv\Scripts\python scripts\generate_synthetic_data.py
.\.venv\Scripts\python scripts\load_database.py
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\python scripts\run_evaluation.py
```

首次体验只要求前两条数据命令成功，然后即可启动 UI / API（见下文「4. 启动三种入口」）。
提交代码或验证结果口径时，再运行 pytest 与离线评估。

---

## 3. 数据文件清单与版本控制策略

### 3.1 每个文件在哪、是什么

| 位置 | 含义 |
|---|---|
| `data/raw/assets.csv` | 25 台资产主数据（`A001`–`A025`：名称、类型、产线、部门、厂商、关键度、状态） |
| `data/raw/work_orders.csv` | 工单（约 280–340 条：症状、诊断、动作、停机时长、状态） |
| `data/raw/meter_readings.csv` | 仪表读数（180 天、2 小时采样；约 1.5% 缺失值 + 少量重复行） |
| `data/raw/maintenance_plans.csv` | 预防性维护计划（时间/用量触发、下次到期） |
| `data/raw/task_groups.csv` | 维护任务组（含 `safety_critical` 安全关键标记） |
| `data/raw/parts.csv` | 备件（成本、库存、再订货点） |
| `data/raw/asset_parts.csv` | 资产–备件关系（类似 BOM） |
| `data/raw/part_usage.csv` | 备件消耗记录 |
| `data/raw/events.csv` | 事件（报警 / 间歇停机等，当前**没有**对应的只读工具） |
| `data/raw/ground_truth_failures.csv` | **评估专用** ground truth（失效模式 + 相关证据 id）；不入库、不进镜像、不暴露给 Agent/UI |
| `data/docs/*.md` | 5 篇**虚构**维修文档（液压机手册、润滑 SOP、传感器排障、预防性维护策略、安全规程） |
| `data/industrial.db` | SQLite 数据库（由 `load_database.py` 生成；运行时以 `mode=ro` 只读打开） |
| `traces/*.json` | 每次运行的 `TraceRecord` 快照（只读、不可重放；文件名即 `request_id`） |
| `docs/EVALUATION_REPORT.md` | 离线评估原始报告（由 `run_evaluation.py` 生成，可覆盖） |

### 3.2 生成 / 忽略 / 提交 策略

| 类别 | 文件 | 说明 |
|---|---|---|
| **生成**（脚本每次覆盖写入） | `data/raw/*.csv`、`data/industrial.db`、`traces/*.json`、`docs/EVALUATION_REPORT.md` | 重新跑对应脚本即可重建 |
| **忽略**（`.gitignore` 已排除） | `data/raw/*.csv`、`data/industrial.db`、`traces/*.json`、`.venv/`、`.env`、`__pycache__/`、`.pytest_cache/`、`/test_deepseek.py` | 不入库 |
| **提交**（已入库） | `data/docs/*.md`、`data/.gitkeep`、`traces/.gitkeep`、`docs/*.md`（含 `EVALUATION_REPORT.md`） | 手写/评审内容与生成报告一并入库 |

> 注意 `docs/EVALUATION_REPORT.md` 是「生成物但已提交」：重新跑 `run_evaluation.py` 会覆盖它，
> 若只改评估逻辑不更新文档会与 `EVALUATION_METHODOLOGY.md` 冲突（方法论里明确要求同步更新）。

---

## 4. 启动三种入口

### 4.1 Streamlit UI（推荐第一次体验）

```powershell
.\.venv\Scripts\python -m streamlit run ui/streamlit_app.py
```

浏览器打开默认地址 `http://localhost:8501`。若端口被占用用 `--server.port 8502` 换端口。

### 4.2 FastAPI

```powershell
.\.venv\Scripts\python -m uvicorn src.api.main:app --reload
```

- 健康检查：`http://127.0.0.1:8000/health` → `{"status":"ok"}`
- 交互式文档：`http://127.0.0.1:8000/docs`
- 主要接口：`POST /agent/query`、`POST /actions/{id}/approve` / `reject`、
  `GET /traces/{request_id}`、`GET /assets/{asset_id}`、`GET /work-orders`、`GET /meter-summary`

> 当前 API **无认证**；`pending` 审批表是进程内 `dict`，重启即丢、多 worker 不共享。

### 4.3 Docker（本地 Compose 已验证）

```powershell
docker compose up --build
```

构建时会生成数据并删除 ground truth。当前 Compose 入口为：

- API 根路径 / Swagger：`http://localhost:8001/`（根路径重定向到 `/docs`）
- API health：`http://localhost:8001/health`
- Streamlit：`http://localhost:8502/`

已在本机完成镜像 build、容器 recreate 和 API/UI 健康检查。该结论不代表生产部署、CI 验证或 SLA。

---

## 5. 页面逐页指南

页面左侧导航包含四页：**资产与数据 / Agent 任务 / 运行记录 / 使用说明**。侧栏同时显示
当前模式（确定性、无 LLM）、数据库状态和当前资产；“清除会话”会清除当前 Agent 结果、
当前选择、筛选/导航和本次浏览器会话中的运行快照，同时刷新 cached runner。运行中重建数据或
维修文档后，应执行该操作或重启 Streamlit。

### 5.1 资产与数据

这是第一次打开页面后的起点，不需要事先知道资产编号。

1. 页面顶部显示全部 25 台资产目录，可按**线体、部门、类型、关键性、状态**筛选。
2. “选择资产”下拉框只显示当前筛选结果，标签包含资产编号、名称和线体。
3. 选择资产后查看基本信息、最近工单、仪表历史和仪表汇总。
4. 工单窗口可选 7 / 30 / 90 / 180 天；无工单只表示当前窗口没有记录，不代表设备没有问题。
5. 仪表窗口可选 7 / 30 / 90 天；信号可选温度、压力、振动、电流，图表与表格都标注单位。
6. 可下载当前仪表窗口的 CSV。仪表汇总对比 30 或 90 天基线与最近 7 天，显示变化百分比、
   每日趋势方向和缺失数。

页面的“汇总口径说明”解释了时间锚点、最近 7 天窗口、缺失/重复数据和“趋势不等于诊断”。
切换资产会清除旧的 Agent 结果，避免把上一台设备的结论误认为当前设备结果。

### 5.2 Agent 任务

1. 先在“资产与数据”选择资产，再进入本页。
2. 从四个“问题措辞示例”中选择一句；它们都运行同一套 fixed-plan，不代表四种不同能力。
3. 任务文本会自动带入当前资产编号，也可编辑；运行前会强制验证文本必须且只能包含当前所选资产。
   小写 `a001` 会规范为 `A001`；缺少编号或同时出现其他资产会在页面就地报错，不会执行。
4. 点击“运行分析”，等待固定四工具流程完成。
5. 依次阅读最终回答、工具调用、假设、证据、待处理动作和“结果自检”。
6. “标记已复核：同意/拒绝提案”只修改当前浏览器会话中的提案状态；按钮完成一次决定后会禁用，且不会产生外部写入。

本页不是开放式 LLM 聊天。四种措辞示例都经过同一套确定性 fixed-plan，只用于帮助用户提出可读问题，
不是四种不同的模型能力。

Agent 的数据窗口固定为：最近 37 天 meter 读取，综合时比较最近 7 天与此前 30 天基线；工单查询
固定为最近 30 天。资产页的 7/30/90 天图表和 30/90 天汇总选项只改变人类浏览视图，**不会**
改变 Agent 输入。图表附近“确定性规则阈值”折叠区列出信号阈值、工单关键词加分和置信度分档；
关键词表与完整实现仍以 `src/agent/synthesizer.py` 为准。这些阈值不是设备厂家限值。

### 5.3 运行记录

页面分为两类记录：

- **本次会话快照**：记录任务时间、资产、任务、状态、证据数和待办；关闭会话或重启后可能丢失。
- **持久化 Trace**：读取 `traces/*.json`。`eval-*` 标为“基准评估”，其他记录标为“会话”。

选择 trace 后可查看投影工具调用、假设原因、证据 ID 和完整 trace 投影。Trace 只包含投影字段，
不是完整 `AgentState`，也不是审批审计、checkpoint 或 memory；同意/拒绝的复核结果不会写回 trace。

### 5.4 使用说明

页面内置首次运行命令、数据路径和正确性口径的简版说明；完整版本就是本文件
[USER_GUIDE_CN.md](USER_GUIDE_CN.md)。

---

## 6. 读结果：工具 / 证据 / 假设 / 建议核查步骤 / 输出结构自检

一次成功的运行（例如 `A001 stopped this week...`）会产出以下可读对象：

| 对象 | 在哪看 | 含义与注意点 |
|---|---|---|
| **工具调用 tool_calls** | UI“工具调用”表 / Trace | 固定 4 个只读工具：`get_asset`、`search_recent_work_orders`、`get_meter_history`、`search_docs` |
| **证据 evidence** | UI“证据”表 / API `state.evidence` | 带 `source_type` 与稳定 `source_id`；DOCUMENT 证据**不参与**根因打分 |
| **假设 hypotheses** | UI“假设”卡片 | top-3，每条显示中英原因、confidence、中文原因说明、建议核查步骤与关联引用 |
| **待审批动作 pending_action** | UI 红色强调的“待处理动作”区域 | `PENDING_APPROVAL` 起步；标记同意/拒绝只改会话内存态，不触发外部写 |
| **输出结构自检** | UI“结果自检”表 | 只检查资产解析、工具状态、证据存在和关联引用可解析，不判断诊断正确性或执行安全 |

**读假设时请记住**：`supporting_evidence_ids` 是「可追溯引用」，不等于「文档支撑了结论」；
当前检索文档不驱动推理（claim grounding 弱）。不要把带 id 的引用说成强证据落地。

---

## 7. 重新生成与处理数据

| 想做的事 | 命令 |
|---|---|
| 重新生成合成数据（覆盖 `data/raw/*.csv` 与 `data/docs/*.md`） | `.\.venv\Scripts\python scripts\generate_synthetic_data.py` |
| 重新入库（drop + recreate 各表，覆盖 `data/industrial.db`） | `.\.venv\Scripts\python scripts\load_database.py` |
| 重新跑离线评估（覆盖 `docs/EVALUATION_REPORT.md` 与 `traces/eval-*.json`） | `.\.venv\Scripts\python scripts\run_evaluation.py` |
| 完整重建（一步到位） | 依次执行上面三条，再跑 `-m pytest` |

生成器是确定性（固定 seed `42`）、幂等（覆盖输出）。「最近 N 天」以数据内
`MAX(timestamp)` 为基准（数据时间范围约 `2025-12-01` 起 180 天），**不按你电脑的当前日期**。

---

## 8. 验证结果

### 8.1 pytest（当前基线 71 通过）

```powershell
.\.venv\Scripts\python -m pytest
```

期望输出 `71 passed`。这验证的是**完整性与内部一致性**：各组件按自己声明的行为工作、
不崩溃、契约自洽。

### 8.2 离线评估（30 场景）

```powershell
.\.venv\Scripts\python scripts\run_evaluation.py
```

跑 30 个场景（25 台资产 + missing / ambiguous / prompt-injection / duplicate /
unauthorized-write），写报告到 [EVALUATION_REPORT.md](EVALUATION_REPORT.md)。

### 8.3 指标：七项 + 总数

共 **7 项质量指标** + 1 个场景计数 `total_scenarios`（`MetricsSnapshot` 共 8 个字段；
`total_scenarios=30` 是计数，不是准确率指标）。

| 指标 | 当前值 | 一句话口径 |
|---|---|---|
| asset_resolution_accuracy | 1.0 | 确定性正则解析，非模型能力 |
| root_cause_top1 / top3 | 1.0 | 与合成数据同源，**循环** |
| evidence_recall | 0.3698 | **真实、可解读**（缺 events 工具 + WO 窗口/截断） |
| tool_selection_accuracy | 1.0 | 固定 4-tool plan，**静态 / 代理** |
| safety_gate_compliance | 1.0 | 只查门态，非执行级安全 |
| recovery_rate | 1.0 | 确定性分支终态断言，**代理** |

**各指标精确分子 / 分母与完整 caveat 委托给** [EVALUATION_METHODOLOGY.md](EVALUATION_METHODOLOGY.md)
（避免在此重复易碎公式）。请以那份文档为唯一权威口径。

### 8.4 报告 caveat 与完整性 / 内部一致性 vs 正确性的区分

- **报告自带 caveat**：[EVALUATION_REPORT.md](EVALUATION_REPORT.md) 开头的 `Caveats` 一节已明确：
  确定性无 LLM、合成同源数据、top-k 循环风险、固定 plan 代理、门态非执行安全、场景级恢复非重试、
  recall 只测覆盖不测引用正确性、以及「未报告」的项（延迟 / token / 成本 / 引用精度等）。
- **完整性 / 内部一致性**：pytest 全绿 + 30 场景全部到达预期终态 + 报告完整生成。这证明
  「系统按声明运行、没崩、组件自洽」。
- **正确性**：能反映真实能力的只有 `evidence_recall=0.3698` 与「检索文档不参与打分」这两点；
  其余 = 1.0 的指标在确定性 + 合成数据设定下是静态 / 循环 / 代理，**不能**当作对真实维修数据的
  诊断正确性证据。对外表述时请用「合成数据上的回归自检」，不要宣称泛化或生产可用。

### 8.5 检查 trace

```powershell
.\.venv\Scripts\python -c "import json; print(json.load(open('traces/eval-asset_A001.json')))"
```

或用 UI 的「运行记录」页选择对应 request。trace 用于**诊断一次运行的内部过程**，不是审计、
不是检查点、不是记忆。

---

## 9. 排障

| 症状 | 原因与解决 |
|---|---|
| 启动报 `unable to open database file` / 找不到 `data/industrial.db` | 还没入库。先跑 `generate_synthetic_data.py` 再跑 `load_database.py` |
| 运行记录为空 | 还没跑过 Agent 或评估。先在“Agent 任务”运行一次分析，或跑 `run_evaluation.py` 生成 `eval-*` trace |
| 查某资产工单 / 读数为空 | 合法范围是 `A001`–`A025`；且「最近 N 天」按数据内最新时间戳（约 2026-05-30）计算，不是今天。若资产 id 拼错会提示 `Asset not found` |
| 本地端口冲突（8000 / 8501） | Uvicorn 可用 `--port 8002`；Streamlit 可用 `--server.port 8503` |
| Docker 起不来 / `daemon` 报错 | 确认 Docker Desktop 已启动；本项目已验证的 Compose 端口是 API 8001、UI 8502 |
| 标记已复核后刷新页面或重启，审批状态/历史不见了 | 审批是会话内内存态（UI 用 `st.session_state`，API 用进程内 `dict`），重启即丢，这是设计内的边界 |
| `docs/EVALUATION_REPORT.md` 看起来过期 / 与代码不一致 | 重新跑 `run_evaluation.py` 覆盖；改指标逻辑时必须同步 `EVALUATION_METHODOLOGY.md` 与报告（方法论要求） |
| 想看某个 request 的 trace 报 404 | 该 `request_id` 不在当前进程的 `traces/` 下；审批动作只在当前进程内存中，重启后 `/actions/{id}/approve` 会 404 |

---

## 10. 5 分钟演示脚本

```powershell
# 1) 装依赖（首次）
python -m venv .venv
.\.venv\Scripts\python -m pip install -r requirements.txt

# 2) 生成 + 入库
.\.venv\Scripts\python scripts\generate_synthetic_data.py
.\.venv\Scripts\python scripts\load_database.py

# 3) 自检与评估（约几秒）
.\.venv\Scripts\python -m pytest                  # 期望 71 passed
.\.venv\Scripts\python scripts\run_evaluation.py  # 期望 30 scenarios

# 4) 起 UI（另开一个终端）
.\.venv\Scripts\python -m streamlit run ui/streamlit_app.py
```

浏览器打开 `http://localhost:8501`：

1. 在“资产与数据”浏览 25 台资产，用筛选器缩小目录并选择 `A001`。
2. 切换 30/90 天仪表窗口，查看温度、压力、振动、电流图表、原始数据和基线汇总。
3. 进入“Agent 任务”，选择“工单 + 仪表证据”，点击“运行分析”。
4. 查看工具调用、top-3 假设、关联引用和结果自检；若有待处理动作，点击“标记已复核：同意提案”（仅记录会话决定）。
5. 进入“运行记录”，找到本次会话快照，并在持久化 Trace 中检查工具、假设原因和证据 ID。

---

## 11. 文档索引

- [README.md](../README.md) — 项目概览与快速开始
- [HANDBOOK.md](HANDBOOK.md) — 当前实现综合参考（架构 / 契约 / API 权威细节版）
- [EVALUATION_METHODOLOGY.md](EVALUATION_METHODOLOGY.md) — 指标分子 / 分母与所有 caveat 的唯一权威来源
- [EVALUATION_REPORT.md](EVALUATION_REPORT.md) — 离线评估原始报告（生成物）
- [SAFETY_AND_THREAT_MODEL.md](SAFETY_AND_THREAT_MODEL.md) — 安全与威胁模型
- [CAPABILITY_MATRIX.md](CAPABILITY_MATRIX.md) — 能力矩阵
- [NEXT_PHASES.md](NEXT_PHASES.md) — 后续阶段（LLM / heldout / CI / 生产写 blocker）
