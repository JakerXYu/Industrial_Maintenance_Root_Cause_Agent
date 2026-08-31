"""Streamlit 工业维护根因分析控制台（中文优先，v0 确定性、无 LLM）。

v0 简化（ponytail）：本 UI 直接调用 ``AgentRunner`` 与 ``Repository``，不经
FastAPI HTTP 层；这是刻意的单入口简化，升级触发条件为「需要与 API/多进程共享
审批状态或鉴权」时再改走 HTTP 契约。审批仅存在于当前会话内存态，无外部写入。
"""

from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent import policy
from src.agent.runner import AgentRunner
from src.analytics.trend import compute_meter_summary
from src.contracts import MeterSummaryRequest
from src.db.repository import Repository

DB_PATH = ROOT / "data" / "industrial.db"
TRACES_DIR = ROOT / "traces"

PAGES = ["资产与数据", "Agent 任务", "运行记录", "使用说明"]

# ---------------------------------------------------------------------------
# 中文枚举 / 单位映射（仅 UI 展示层，不改动后端契约）
# ---------------------------------------------------------------------------
_ASSET_TYPE_ZH = {
    "hydraulic_press": "液压机",
    "robotic_welding_cell": "机器人焊接单元",
    "cnc_machine": "CNC 机床",
    "industrial_pump": "工业泵",
}
_ASSET_CRITICALITY_ZH = {"low": "低", "medium": "中", "high": "高", "critical": "关键"}
_ASSET_STATUS_ZH = {
    "active": "在用",
    "inactive": "停用",
    "under_maintenance": "维护中",
    "retired": "退役",
}
_WO_TYPE_ZH = {"corrective": "纠正性", "preventive": "预防性", "inspection": "巡检", "emergency": "应急"}
_WO_STATUS_ZH = {"open": "待处理", "in_progress": "进行中", "completed": "已完成", "cancelled": "已取消"}
_PRIORITY_ZH = {"low": "低", "medium": "中", "high": "高", "urgent": "紧急"}
_ACTION_TYPE_ZH = {
    "CREATE_WORK_ORDER": "创建工单",
    "UPDATE_WORK_ORDER": "更新工单",
    "CREATE_PART_ORDER": "创建备件订单",
    "SCHEDULE_MAINTENANCE": "安排维护",
}
_APPROVAL_ZH = {"PENDING_APPROVAL": "待审批", "APPROVED": "已批准", "REJECTED": "已拒绝"}
_CONFIDENCE_ZH = {"low": "低", "medium": "中", "medium-high": "中高", "high": "高"}
_AGENT_STATUS_ZH = {
    "initialized": "已初始化",
    "resolved": "已解析",
    "planned": "已计划",
    "executed": "已执行",
    "synthesized": "已合成",
    "complete": "完成",
    "error": "错误",
}
_EVIDENCE_SOURCE_ZH = {
    "asset": "资产",
    "work_order": "工单",
    "meter": "仪表",
    "maintenance_plan": "维护计划",
    "part": "备件",
    "event": "事件",
    "document": "文档",
}
_SIGNAL_ZH = {"temperature_c": "温度", "pressure_bar": "压力", "vibration_rms": "振动", "current_a": "电流"}
_SIGNAL_UNIT = {"temperature_c": "°C", "pressure_bar": "bar", "vibration_rms": "mm/s RMS", "current_a": "A"}
_CAUSE_ZH = {
    "Lubrication degradation": "润滑状态退化",
    "Hydraulic leakage": "液压泄漏",
    "Position sensor instability": "位置传感器不稳定",
    "Bearing degradation": "轴承状态退化",
    "Cooling degradation": "冷却能力退化",
    "Normal operation / false alarm": "正常运行或误报",
}
_CHECK_ZH = {
    "Inspect lubrication pressure and filter condition": "检查润滑压力和过滤器状态",
    "Verify lubrication flow rate": "核对润滑流量",
    "Run 20 controlled cycles and compare temperature/friction trend": "运行 20 个受控循环并比较温度/摩擦趋势",
    "Inspect hydraulic seals and connections for leakage": "检查液压密封和连接处是否泄漏",
    "Verify hydraulic pressure during a controlled cycle": "在受控循环中核对液压压力",
    "Inspect sensor wiring and connector": "检查传感器线缆和连接器",
    "Verify sensor mount and compare to a reference sensor": "检查传感器安装并与参考传感器对比",
    "Measure bearing temperature and vibration trend": "测量轴承温度和振动趋势",
    "Inspect bearing condition and lubrication": "检查轴承状态和润滑情况",
    "Check coolant level and flow": "检查冷却液液位和流量",
    "Inspect cooling fan and heat exchanger": "检查冷却风扇和换热器",
    "Continue monitoring for recurrence": "继续监测是否再次出现",
    "Verify instrumentation before escalating": "升级处理前先核对仪表状态",
}

# ---------------------------------------------------------------------------
# 集中式 CSS：中性底色 + 克制的红色强调，无渐变/玻璃/emoji
# ---------------------------------------------------------------------------
_CSS = """
<style>
.stApp { background-color: #f4f5f7; color: #1f2329; }
[data-testid="stSidebar"] { background-color: #e9ebee; border-right: 1px solid #d5d8dc; }
[data-testid="stSidebar"] * { color: #1f2329; }
h1, h2, h3, h4 { color: #1f2329; }
a { color: #b3261e; }
[data-testid="stMetricValue"] { color: #1f2329; }
a:focus-visible, button:focus-visible, input:focus-visible, textarea:focus-visible,
select:focus-visible, [data-testid="stWidgetLabel"]:focus-visible,
[role="radiogroup"]:focus-visible, [data-testid="stDownloadButton"]:focus-visible {
    outline: 2px solid #b3261e !important;
    outline-offset: 2px;
}
.pending-action-title {
    color: #b3261e;
    font-weight: 600;
    font-size: 1rem;
    margin-bottom: 0.5rem;
}
div[data-testid="stVerticalBlockBorderWrapper"] { border-color: #d5d8dc; }
@media (max-width: 768px) {
    .block-container { padding-left: 1rem; padding-right: 1rem; }
    [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
}
</style>
"""

st.set_page_config(page_title="工业维护根因分析控制台", layout="wide")
st.markdown(_CSS, unsafe_allow_html=True)


@st.cache_resource
def get_runner() -> AgentRunner:
    """v0：直接构造 Repository + AgentRunner（HTTP 层不参与）。"""
    return AgentRunner(Repository(DB_PATH), TRACES_DIR)


def _clear_session() -> None:
    get_runner.clear()
    st.session_state.clear()


def _distinct(assets, key_fn):
    seen = []
    for a in assets:
        value = key_fn(a)
        if value not in seen:
            seen.append(value)
    return seen


def _catalog_frame(assets) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "资产编号": a.asset_id,
                "资产名称": a.asset_name,
                "类型": _ASSET_TYPE_ZH.get(a.asset_type.value, a.asset_type.value),
                "线体": a.line,
                "部门": a.department,
                "制造商": a.manufacturer,
                "型号": a.model,
                "安装日期": a.install_date.isoformat(),
                "关键性": _ASSET_CRITICALITY_ZH.get(a.criticality.value, a.criticality.value),
                "状态": _ASSET_STATUS_ZH.get(a.status.value, a.status.value),
            }
            for a in assets
        ]
    )


def _wo_frame(orders) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "工单编号": o.wo_id,
                "创建时间": o.created_at,
                "完成时间": o.completed_at,
                "类型": _WO_TYPE_ZH.get(o.wo_type.value, o.wo_type.value),
                "优先级": _PRIORITY_ZH.get(o.priority.value, o.priority.value),
                "症状": o.symptom,
                "诊断": o.diagnosis or "-",
                "处理措施": o.action_taken or "-",
                "停机(分)": o.downtime_min,
                "状态": _WO_STATUS_ZH.get(o.status.value, o.status.value),
            }
            for o in orders
        ]
    )


def _meter_frame(readings) -> pd.DataFrame:
    df = pd.DataFrame(
        [
            {
                "时间": r.timestamp,
                "循环数": r.cycle_count,
                "运行小时": r.runtime_hours,
                "温度(°C)": r.temperature_c,
                "压力(bar)": r.pressure_bar,
                "振动(mm/s RMS)": r.vibration_rms,
                "电流(A)": r.current_a,
            }
            for r in readings
        ]
    )
    if not df.empty:
        df = df.sort_values("时间", ascending=False).reset_index(drop=True)
    return df


def _signal_chart(readings, signal):
    points = []
    for r in readings:
        value = getattr(r, signal)
        if value is not None:
            points.append({"时间": r.timestamp, signal: value})
    if not points:
        return None
    return pd.DataFrame(points)


def _summary_frame(summary) -> pd.DataFrame:
    def trend_direction(slope) -> str:
        if slope is None:
            return "不可计算"
        daily_slope = slope * 86400
        if abs(daily_slope) < 1e-6:
            return "平稳"
        return "上升" if daily_slope > 0 else "下降"

    return pd.DataFrame(
        [
            {
                "信号": f"{_SIGNAL_ZH.get(key, key)} ({_SIGNAL_UNIT.get(key, '')})",
                "基线均值": round(s.baseline_mean, 3),
                "近7日均值": round(s.recent_mean, 3),
                "变化(%)": round(s.relative_change_pct, 2) if s.relative_change_pct is not None else None,
                "趋势方向": trend_direction(s.trend_slope),
                "趋势(变化/天)": round(s.trend_slope * 86400, 4) if s.trend_slope is not None else None,
                "近7天缺失数": s.missing_count,
            }
            for key, s in summary.signals.items()
        ]
    )


def _task_templates(asset_id):
    return [
        (
            "近期仪表变化",
            f"{asset_id} 最近仪表读数与基线相比是否出现明显变化？请分析温度、压力、振动与电流的趋势。",
        ),
        (
            "工单 + 仪表证据",
            f"{asset_id} 结合最近工单与仪表数据，给出可能的失效原因，并列出支撑证据。",
        ),
        (
            "数据缺失与局限",
            f"{asset_id} 当前数据是否存在缺失或局限？请说明可用证据与局限，避免过度结论。",
        ),
        (
            "人工复核处置建议",
            f"{asset_id} 基于现有证据提出需要人工复核的处置建议（不自动执行任何写操作）。",
        ),
    ]


def _cause_label(cause: str) -> str:
    translated = _CAUSE_ZH.get(cause)
    return f"{translated}（{cause}）" if translated else cause


def _rationale_zh(rationale: str) -> str:
    if rationale == "no decisive signal deviation; classification based on work-order notes":
        return "未发现决定性信号偏差；当前分类主要依据工单记录。"
    replacements = {
        "hydraulic pressure is ": "液压压力相对基线变化 ",
        "temperature is ": "温度相对基线变化 ",
        "vibration is ": "振动相对基线变化 ",
        " vs baseline": "",
    }
    translated = rationale
    for source, target in replacements.items():
        translated = translated.replace(source, target)
    return translated.replace("; ", "；")


def _answer_zh(state) -> str:
    if not state.hypotheses:
        return "现有证据不足，无法形成候选假设。"
    top = state.hypotheses[0]
    action_text = "系统生成了待人工复核的动作提案。" if state.pending_action else "系统未生成工单提案。"
    return (
        f"共形成 {len(state.hypotheses)} 个候选假设；首位为 {_cause_label(top.cause)}，"
        f"置信度为 {_CONFIDENCE_ZH.get(top.confidence.value, top.confidence.value)}。{action_text}"
    )


# ---------------------------------------------------------------------------
# 页面渲染
# ---------------------------------------------------------------------------
def render_assets(runner: AgentRunner) -> None:
    st.subheader("资产目录")
    assets = runner.repo.list_assets(100)
    if not assets:
        st.warning("数据库中没有资产数据。请先生成并加载数据。")
        return

    lines = _distinct(assets, lambda a: a.line)
    departments = _distinct(assets, lambda a: a.department)
    types = _distinct(assets, lambda a: a.asset_type.value)
    crits = _distinct(assets, lambda a: a.criticality.value)
    statuses = _distinct(assets, lambda a: a.status.value)

    c1, c2, c3 = st.columns(3)
    c4, c5 = st.columns(2)
    fl = c1.selectbox("线体", ["全部"] + lines, key="filter_line")
    fd = c2.selectbox("部门", ["全部"] + departments, key="filter_department")
    ft = c3.selectbox(
        "类型",
        ["全部"] + types,
        format_func=lambda value: "全部" if value == "全部" else _ASSET_TYPE_ZH.get(value, value),
        key="filter_type",
    )
    fc = c4.selectbox(
        "关键性",
        ["全部"] + crits,
        format_func=lambda value: "全部" if value == "全部" else _ASSET_CRITICALITY_ZH.get(value, value),
        key="filter_criticality",
    )
    fs = c5.selectbox(
        "状态",
        ["全部"] + statuses,
        format_func=lambda value: "全部" if value == "全部" else _ASSET_STATUS_ZH.get(value, value),
        key="filter_status",
    )

    filtered = [
        a
        for a in assets
        if (fl == "全部" or a.line == fl)
        and (fd == "全部" or a.department == fd)
        and (ft == "全部" or a.asset_type.value == ft)
        and (fc == "全部" or a.criticality.value == fc)
        and (fs == "全部" or a.status.value == fs)
    ]

    if not filtered:
        st.info("筛选无匹配结果。请调整筛选条件。")
        if st.session_state.selected_asset_id is not None:
            st.session_state.selected_asset_id = None
            st.session_state.agent_state = None
            for key in ("task_text", "_prev_template", "_prev_asset"):
                st.session_state.pop(key, None)
        return
    else:
        st.caption(f"共 {len(filtered)} / {len(assets)} 个资产")
        st.dataframe(_catalog_frame(filtered), hide_index=True, width="stretch")

    st.subheader("资产详情")
    asset_ids = [a.asset_id for a in filtered]
    by_id = {a.asset_id: a for a in filtered}

    def _label(aid: str) -> str:
        a = by_id[aid]
        return f"{a.asset_id} · {a.asset_name} · {a.line}"

    current_id = st.session_state.selected_asset_id
    options = [""] + asset_ids
    default_index = options.index(current_id) if current_id in options else 0
    selected_id = st.selectbox(
        "选择资产",
        options=options,
        index=default_index,
        format_func=lambda value: "请选择资产" if not value else _label(value),
        key="asset_select",
    )
    if current_id != selected_id:
        st.session_state.agent_state = None
        for key in ("task_text", "_prev_template", "_prev_asset"):
            st.session_state.pop(key, None)
    st.session_state.selected_asset_id = selected_id
    if not selected_id:
        st.info("请从筛选结果中明确选择一台资产，再查看历史数据或运行分析。")
        return
    render_asset_detail(runner, by_id[selected_id])


def render_asset_detail(runner: AgentRunner, asset) -> None:
    st.markdown(f"### {asset.asset_id} · {asset.asset_name}")

    cols = st.columns(4)
    cols[0].metric("关键性", _ASSET_CRITICALITY_ZH.get(asset.criticality.value, asset.criticality.value))
    cols[1].metric("状态", _ASSET_STATUS_ZH.get(asset.status.value, asset.status.value))
    cols[2].metric("类型", _ASSET_TYPE_ZH.get(asset.asset_type.value, asset.asset_type.value))
    cols[3].metric("安装日期", asset.install_date.isoformat())
    st.markdown(f"- 线体：{asset.line}　·　部门：{asset.department}")
    st.markdown(f"- 制造商：{asset.manufacturer}　·　型号：{asset.model}")

    # 最近工单（days 固定为 7/30/90/180，limit 上限 100）
    st.markdown("**最近工单**")
    wo_days = st.selectbox("工单时间范围（天）", [7, 30, 90, 180], key="wo_days")
    orders = runner.repo.search_recent_work_orders(asset.asset_id, wo_days, 100)
    with st.expander(f"查看最近 {wo_days} 天工单（{len(orders)} 条）"):
        if orders:
            st.dataframe(_wo_frame(orders), hide_index=True, width="stretch")
        else:
            st.info(f"最近 {wo_days} 天内暂无工单记录。")

    # 仪表历史（days 固定为 7/30/90，limit 安全上限 5000）
    st.markdown("**仪表历史**")
    meter_days = st.selectbox("仪表时间范围（天）", [7, 30, 90], key="meter_days")
    readings = runner.repo.get_recent_meter_readings(asset.asset_id, meter_days, 5000)
    if readings:
        signal = st.selectbox(
            "选择信号",
            list(_SIGNAL_ZH.keys()),
            format_func=lambda s: f"{_SIGNAL_ZH[s]} ({_SIGNAL_UNIT[s]})",
            key="meter_signal",
        )
        chart_df = _signal_chart(readings, signal)
        if chart_df is not None and not chart_df.empty:
            st.line_chart(
                chart_df,
                x="时间",
                y=signal,
            )
            st.caption(f"横轴：时间；纵轴：{_SIGNAL_ZH[signal]}（{_SIGNAL_UNIT[signal]}）")
        else:
            st.info(f"该信号在最近 {meter_days} 天内无读数。")
        st.caption(
            f"实际窗口：{readings[0].timestamp:%Y-%m-%d %H:%M} 至 {readings[-1].timestamp:%Y-%m-%d %H:%M}；"
            f"样本数：{len(readings)}。当前未配置设备级正常范围或告警限值。"
        )
        with st.expander("查看确定性规则阈值（启发式，不是设备限值）"):
            st.markdown("- 每命中一个对应失效模式的工单关键词，该候选 +2 分。")
            st.markdown("- 压力相对基线低于 -5%：液压泄漏候选 +4 分。")
            st.markdown("- 温度高于 +3%：冷却 +2、润滑 +1、轴承 +1；温度高于 +2% 时润滑再 +1。")
            st.markdown("- 振动高于 +5%：轴承 +3；振动在 0%～+5%：润滑 +1。")
            st.markdown("- 温度 >+3%、压力 <-5% 或振动 >+3% 视为存在信号异常；否则正常/误报候选 +4。")
            st.markdown("- 置信度分档：得分 ≥8 为高，≥5 为中高，≥3 为中，其余为低。")
            st.caption("关键词表与完整规则以 src/agent/synthesizer.py 为准。")
        raw_df = _meter_frame(readings)
        with st.expander("查看与下载原始仪表数据"):
            st.dataframe(raw_df, hide_index=True, width="stretch")
            csv_bytes = raw_df.to_csv(index=False).encode("utf-8-sig")
            st.download_button(
                "下载 CSV",
                data=csv_bytes,
                file_name=f"{asset.asset_id}_meter_{meter_days}d.csv",
                mime="text/csv",
                key="download_meter_csv",
            )
    else:
        st.info(f"最近 {meter_days} 天内暂无仪表读数。")

    # 仪表汇总（基线 vs 近 7 天）
    st.markdown("**仪表汇总（基线 vs 近 7 天）**")
    baseline_days = st.selectbox("汇总基线窗口（天）", [30, 90], key="summary_days")
    summary_readings = runner.repo.get_recent_meter_readings(
        asset.asset_id, baseline_days + 7, 5000
    )
    summary = compute_meter_summary(
        summary_readings,
        MeterSummaryRequest(asset_id=asset.asset_id, days=baseline_days),
    )
    if summary.signals:
        st.dataframe(_summary_frame(summary), hide_index=True, width="stretch")
    else:
        st.info("无可用信号汇总（读数为空或信号缺失/全为空值）。")
    with st.expander("汇总口径说明"):
        st.markdown("- 锚点：Repository 先按全表最新时间截取窗口，汇总再以当前资产已取回读数的 **MAX(timestamp)** 为「现在」，而非真实当前时间。")
        st.markdown("- 最近窗口：固定为 **7 天**（相对锚点）。")
        st.markdown("- 基线窗口：锚点前推 `baseline_days`（30/90 天，不含最近 7 天）。")
        st.markdown("- 缺失/重复：缺失数仅统计最近 7 天窗口内的空值；重复或稀疏采样会影响均值，未被去重。")
        st.markdown("- 趋势 ≠ 诊断：趋势斜率是统计量，用于观察变化方向；根因诊断由规则打分器结合工单得出，二者不可混同。")


def render_agent(runner: AgentRunner) -> None:
    st.subheader("Agent 任务")
    st.caption("确定性固定计划（get_asset / search_recent_work_orders / get_meter_history / search_docs），无 LLM，不产生真实写入。下面选项只是问题措辞示例，均运行同一套分析流程。")

    asset_id = st.session_state.selected_asset_id
    if not asset_id:
        st.info("请先在「资产与数据」页选择一个资产，再发起任务。")
        return
    asset = runner.repo.get_asset(asset_id)
    if asset is None:
        st.warning("当前选择的资产不存在，请返回资产目录重新选择。")
        return
    st.info(f"当前资产：{asset.asset_id} · {asset.asset_name} · {asset.line} · {asset.department}")
    st.caption(
        "Agent 输入窗口固定：读取最近 37 天仪表数据，在综合阶段比较最近 7 天与此前 30 天基线；"
        "工单固定查询最近 30 天。资产页选择的图表/汇总窗口不会改变 Agent 输入。"
    )

    templates = _task_templates(asset_id)
    template_ids = [t[0] for t in templates]
    template_text = {t[0]: t[1] for t in templates}

    prev_template = st.session_state.get("_prev_template")
    prev_asset = st.session_state.get("_prev_asset")
    chosen = st.radio("问题措辞示例（同一固定基线分析）", template_ids, key="task_template")
    default_text = template_text[chosen]
    if (
        "task_text" not in st.session_state
        or prev_template != chosen
        or prev_asset != asset_id
    ):
        st.session_state.task_text = default_text
        st.session_state._prev_template = chosen
        st.session_state._prev_asset = asset_id

    task_text = st.text_area("任务文本（可编辑）", key="task_text", height=120)

    if st.button("运行分析", key="run_agent"):
        st.session_state.agent_state = None
        normalized_task = re.sub(
            r"\b[aA](\d{3})\b",
            lambda match: f"A{match.group(1)}",
            task_text,
        )
        mentioned_assets = set(re.findall(r"\bA\d{3}\b", normalized_task))
        if mentioned_assets != {asset_id}:
            st.error(
                f"任务必须且只能引用当前资产 {asset_id}；检测到："
                f"{', '.join(sorted(mentioned_assets)) if mentioned_assets else '未包含资产编号'}。"
                "请返回资产目录切换设备，或修正任务文本。"
            )
        else:
            with st.spinner("正在运行确定性分析…"):
                state = runner.run(normalized_task)
            st.session_state.agent_state = state
            _record_history(state, normalized_task)

    _render_results()


def _record_history(state, task_text: str) -> None:
    action = state.pending_action
    pending_label = (
        f"{_ACTION_TYPE_ZH.get(action.action_type.value, action.action_type.value)} / "
        f"{_APPROVAL_ZH.get(action.status.value, action.status.value)}"
        if action
        else "无"
    )
    snapshot = {
        "时间": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "资产": state.asset_id or "-",
        "任务": task_text,
        "状态": _AGENT_STATUS_ZH.get(state.status.value, state.status.value),
        "证据数": len(state.evidence),
        "提案状态（运行时快照）": pending_label,
    }
    st.session_state.history = [snapshot] + st.session_state.get("history", [])


def _render_results() -> None:
    state = st.session_state.agent_state
    if state is None:
        return

    st.subheader("运行结果")
    status_zh = _AGENT_STATUS_ZH.get(state.status.value, state.status.value)
    cols = st.columns(4)
    cols[0].metric("状态", status_zh)
    cols[1].metric("资产", state.asset_id or "-")
    cols[2].metric("假设数", len(state.hypotheses))
    cols[3].metric("证据数", len(state.evidence))

    st.markdown("**中文结果摘要**")
    st.markdown(_answer_zh(state))
    with st.expander("查看原始引擎输出（English）"):
        st.markdown(state.final_answer or "（无回答）")

    st.markdown("**工具调用**")
    if state.tool_calls:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "工具": t.tool,
                        "参数": ", ".join(f"{k}={v}" for k, v in t.args.items()),
                        "状态": t.status,
                        "结果数": t.result_count,
                        "耗时(ms)": t.latency_ms,
                    }
                    for t in state.tool_calls
                ]
            ),
            hide_index=True,
            width="stretch",
        )
    else:
        st.caption("无工具调用记录。")

    st.markdown("**假设（Hypotheses）**")
    if state.hypotheses:
        for i, h in enumerate(state.hypotheses, 1):
            with st.container(border=True):
                st.markdown(
                    f"**{i}. {_cause_label(h.cause)}** · 置信度：{_CONFIDENCE_ZH.get(h.confidence.value, h.confidence.value)}"
                )
                st.markdown(f"原因说明：{_rationale_zh(h.rationale)}")
                st.markdown("建议核查步骤：" + ("；".join(_CHECK_ZH.get(item, item) for item in h.recommended_checks) if h.recommended_checks else "—"))
                st.markdown("关联引用（不等于已验证支撑）：" + (", ".join(h.supporting_evidence_ids) or "无"))
                if h.contradicting_evidence_ids:
                    st.markdown("矛盾证据：" + ", ".join(h.contradicting_evidence_ids))
    else:
        st.caption("未形成假设。")

    st.markdown("**证据（Evidence）**")
    if state.evidence:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "来源类型": _EVIDENCE_SOURCE_ZH.get(e.source_type.value, e.source_type.value),
                        "来源ID": e.source_id,
                        "资产": e.asset_id or "-",
                        "摘要": e.summary,
                        "时间": e.timestamp.isoformat() if e.timestamp else "-",
                        "引用": e.citation or "-",
                    }
                    for e in state.evidence
                ]
            ),
            hide_index=True,
            width="stretch",
        )
        if len({e.source_id for e in state.evidence}) < len(state.evidence):
            st.caption("部分仪表信号共享同一个 meter_summary 引用 ID；请结合每行摘要判断具体信号，不能按 ID 数量推断独立证据数。")
    else:
        st.caption("无证据。")

    _render_pending_action(state)
    _render_self_check(state)


def _approve() -> None:
    st.session_state.agent_state = policy.approve(st.session_state.agent_state, "streamlit-user")


def _reject() -> None:
    st.session_state.agent_state = policy.reject(st.session_state.agent_state, "streamlit-user")


def _render_pending_action(state) -> None:
    action = state.pending_action
    if action is None:
        st.info("本次运行未提出写类动作。")
        return
    with st.container(border=True):
        st.markdown('<div class="pending-action-title">待处理动作（需人工复核）</div>', unsafe_allow_html=True)
        st.markdown(f"- 动作类型：{_ACTION_TYPE_ZH.get(action.action_type.value, action.action_type.value)}")
        st.markdown(f"- 资产：{action.asset_id}")
        top_cause = state.hypotheses[0].cause if state.hypotheses else action.summary
        st.markdown(f"- 摘要：建议人工检查 {_cause_label(top_cause)}")
        st.markdown(f"- 优先级：{_PRIORITY_ZH.get(action.priority.value, action.priority.value)}")
        st.markdown(f"- 状态：{_APPROVAL_ZH.get(action.status.value, action.status.value)}")
        st.warning("“标记已复核”仅记录于当前会话（session），不触发任何外部写入；刷新或重启后不保留，且不会写入 trace 审计。")
        col_a, col_r = st.columns(2)
        decision_made = action.status.value != "PENDING_APPROVAL"
        col_a.button(
            "标记已复核：同意提案",
            key="approve_action",
            on_click=_approve,
            type="primary",
            disabled=decision_made,
        )
        col_r.button(
            "标记已复核：拒绝提案",
            key="reject_action",
            on_click=_reject,
            disabled=decision_made,
        )


def _render_self_check(state) -> None:
    st.markdown("**结果自检（仅完整性与内部一致性）**")
    evidence_ids = {e.source_id for e in state.evidence}
    referenced = set()
    for h in state.hypotheses:
        referenced.update(h.supporting_evidence_ids)
        referenced.update(h.contradicting_evidence_ids)
    unresolved = referenced - evidence_ids

    tools_ok = bool(state.tool_calls) and all(t.status in ("success", "empty") for t in state.tool_calls)

    checks = [
        ("资产已解析", state.asset_id is not None, f"已定位资产 {state.asset_id}" if state.asset_id else "未定位资产"),
        (
            "工具已完成",
            tools_ok,
            f"{len(state.tool_calls)} 次调用，状态均为成功/空" if tools_ok else "存在失败或未完成的工具调用",
        ),
        ("证据已生成", len(state.evidence) > 0, f"{len(state.evidence)} 条证据" if state.evidence else "无证据"),
        (
            "假设证据引用可解析",
            not unresolved,
            "引用均指向已存在证据" if not unresolved else f"存在无法解析的引用：{sorted(unresolved)}",
        ),
    ]
    rows = [
        {"检查项": name, "结果": "通过" if ok else "未通过", "说明": note}
        for name, ok, note in checks
    ]
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    st.caption("本自检仅评估输出完整性与内部一致性，不判定结果是否「正确」或「准确」。")


def render_history(runner: AgentRunner) -> None:
    st.subheader("运行记录")

    st.markdown("**本次会话快照**")
    history = st.session_state.history
    if history:
        st.dataframe(pd.DataFrame(history), hide_index=True, width="stretch")
    else:
        st.caption("本会话尚未运行任何任务。")

    st.divider()
    st.markdown("**持久化 Trace 记录**（`traces/` 目录）")
    request_ids = runner.traces.list()
    if not request_ids:
        st.caption("暂无持久化 trace。")
        return

    rows = []
    for rid in request_ids:
        try:
            rec = runner.traces.load(rid)
        except Exception:
            rows.append({"类型": "读取失败", "请求ID": rid, "资产": "-", "任务": "-", "状态": "-", "证据ID数": 0, "待办类型": "-"})
            continue
        rows.append(
            {
                "类型": "基准评估" if rid.startswith("eval-") else "会话",
                "请求ID": rid,
                "资产": rec.asset_id or "-",
                "任务": rec.question,
                "状态": _AGENT_STATUS_ZH.get(rec.status, rec.status),
                "证据ID数": len(rec.evidence_ids),
                "待办类型": rec.pending_action_type or "-",
            }
        )
    st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")

    selected_rid = st.selectbox("查看 trace 详情", request_ids, key="trace_select")
    if selected_rid:
        try:
            rec = runner.traces.load(selected_rid)
        except Exception:
            st.warning("该 trace 无法读取。")
            return
        if rec.tool_calls:
            st.markdown("**投影工具调用**")
            st.dataframe(
                pd.DataFrame(
                    [
                        {
                            "工具": t.tool,
                            "参数": ", ".join(f"{k}={v}" for k, v in t.args.items()),
                            "状态": t.status,
                            "结果数": t.result_count,
                            "耗时(ms)": t.latency_ms,
                        }
                        for t in rec.tool_calls
                    ]
                ),
                hide_index=True,
                width="stretch",
            )
        st.markdown("**假设原因**：" + (", ".join(rec.hypothesis_causes) or "无"))
        st.markdown("**证据 ID**：" + (", ".join(rec.evidence_ids) or "无"))
        with st.expander("查看完整 trace 投影"):
            st.json(rec.model_dump())
        st.caption(
            "trace 仅含投影字段（tool_calls / evidence_ids / hypothesis_causes / "
            "pending_action_type），不是完整 AgentState，也不是审批审计记录；审批不会被持久化。"
        )


def render_help() -> None:
    st.subheader("使用说明")

    st.markdown("**快速开始**")
    st.code(
        "python -m venv .venv\n"
        ".\\\\.venv\\\\Scripts\\\\python -m pip install -r requirements.txt\n"
        ".\\\\.venv\\\\Scripts\\\\python scripts\\\\generate_synthetic_data.py\n"
        ".\\\\.venv\\\\Scripts\\\\python scripts\\\\load_database.py\n"
        ".\\\\.venv\\\\Scripts\\\\python -m streamlit run ui/streamlit_app.py",
        language="powershell",
    )

    st.markdown("**数据与文档路径**")
    st.markdown("- 用户指南（中文）：`docs/USER_GUIDE_CN.md`")
    st.markdown("- 原始数据目录：`data/raw`（生成脚本输出的合成 CSV）")
    st.markdown("- SQLite 数据库：`data/industrial.db`（只读，由 load_database.py 生成）")
    st.markdown("- 离线评估报告：`docs/EVALUATION_REPORT.md`")
    st.markdown("- 运行 trace：`traces/`（每次运行的 JSON TraceRecord）")

    st.markdown("**生成与忽略数据**")
    st.markdown("- 合成数据由 `scripts/generate_synthetic_data.py` 生成；评估标注数据生成后不入库、也不出现在本界面。")
    st.markdown("- 数据库以只读模式（`mode=ro`）打开；本界面不修改任何数据。")
    st.markdown("- 运行中重建数据或文档后，请点击侧栏“清除会话”或重启 Streamlit，以清除缓存的 runner。")

    st.markdown("**正确性口径**")
    st.markdown("- 本控制台是确定性 baseline（无 LLM）；指标与假设基于规则打分，不构成生产诊断结论。")


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------
st.session_state.setdefault("selected_asset_id", None)
st.session_state.setdefault("agent_state", None)
st.session_state.setdefault("history", [])

db_ready = DB_PATH.exists()

with st.sidebar:
    st.header("控制台")
    st.caption("模式：确定性固定计划 · 无 LLM")
    st.caption("数据库：" + ("就绪" if db_ready else "缺失"))
    current_asset = st.session_state.selected_asset_id
    st.caption("当前资产：" + (current_asset if current_asset else "未选择"))
    st.button("清除会话", key="clear_session", on_click=_clear_session)
    st.divider()
    page = st.radio("导航", PAGES, key="nav_page")

st.title("工业维护根因分析控制台")
st.caption("从资产目录开始：选择设备、查看历史数据，再运行确定性分析并检查证据。")

if not db_ready:
    st.error("数据库未就绪：未找到 `data/industrial.db`。请先生成并加载数据后刷新。")
    st.code(
        ".\\\\.venv\\\\Scripts\\\\python scripts\\\\generate_synthetic_data.py\n"
        ".\\\\.venv\\\\Scripts\\\\python scripts\\\\load_database.py",
        language="powershell",
    )
    st.stop()

runner = get_runner()

try:
    if page == "资产与数据":
        render_assets(runner)
    elif page == "Agent 任务":
        render_agent(runner)
    elif page == "运行记录":
        render_history(runner)
    else:
        render_help()
except Exception as exc:
    st.error(f"页面读取失败（{type(exc).__name__}）：{exc}")
    st.caption("请检查 data/industrial.db 是否已生成且可读；详细堆栈可在启动 Streamlit 的终端查看。")
