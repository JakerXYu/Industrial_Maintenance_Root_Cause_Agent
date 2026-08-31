"""Streamlit UI tests (AppTest): 中文标题/导航、资产目录与筛选控件、Agent 运行。"""

from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "ui" / "streamlit_app.py"


def _run() -> AppTest:
    return AppTest.from_file(str(APP_PATH), default_timeout=30).run()


def test_chinese_title_and_navigation():
    at = _run()
    assert not at.exception

    titles = [t.value for t in at.title]
    assert "工业维护根因分析控制台" in titles

    nav = at.sidebar.radio[0]
    assert list(nav.options) == ["资产与数据", "Agent 任务", "运行记录", "使用说明"]
    assert nav.value == "资产与数据"


def test_asset_page_catalog_and_select_controls():
    at = _run()
    assert not at.exception

    # 资产选择器：25 个资产，标签含 ID/名称/线体（format_func），无需手填 ID
    asset_select = at.selectbox(key="asset_select")
    assert len(asset_select.options) == 26
    assert asset_select.value == ""
    # 标签同时含 ID、名称、线体
    assert "A001" in asset_select.options[1]
    assert "Line 1" in asset_select.options[1]

    # 五个筛选控件均存在，且首项为「全部」
    for key in (
        "filter_line",
        "filter_department",
        "filter_type",
        "filter_criticality",
        "filter_status",
    ):
        widget = at.selectbox(key=key)
        assert widget is not None
        assert widget.options[0] == "全部"

    # 目录表使用中文列名
    catalog = at.dataframe[0].value
    assert isinstance(catalog, pd.DataFrame)
    assert "资产编号" in catalog.columns
    assert len(catalog) == 25


def test_asset_page_empty_filter_result():
    at = _run()
    assert not at.exception

    # criticality=critical 且 status=under_maintenance 的组合在数据中无匹配
    at.selectbox(key="filter_criticality").set_value("critical").run()
    at.selectbox(key="filter_status").set_value("under_maintenance").run()
    assert not at.exception
    assert any("筛选无匹配结果" in i.value for i in at.info)


def test_asset_filters_constrain_asset_selector():
    at = _run()
    at.selectbox(key="filter_line").set_value("Line 2").run()
    assert not at.exception
    selector = at.selectbox(key="asset_select")
    assert selector.options
    assert selector.value == ""
    assert all("Line 2" in label for label in selector.options[1:])


def test_agent_page_run_default_analysis():
    at = _run()
    assert not at.exception

    at.selectbox(key="asset_select").set_value("A001").run()
    assert not at.exception

    # 切到 Agent 任务页
    at.sidebar.radio[0].set_value("Agent 任务").run()
    assert not at.exception

    # 默认推荐任务已填充（含大写资产 ID A001）
    task_template = at.radio(key="task_template")
    assert len(task_template.options) == 4
    task_text = at.text_area(key="task_text")
    assert task_text.value
    assert "A001" in task_text.value

    # 显式选择 A001 后，不允许文本悄悄切换成 A002
    task_text.set_value("A002 检查最近工单和仪表趋势。")
    at = at.button(key="run_agent").click().run()
    assert not at.exception
    assert any("必须且只能引用当前资产 A001" in e.value for e in at.error)

    at.text_area(key="task_text").set_value("A001 检查最近工单和仪表趋势。")

    # 运行默认推荐分析
    at = at.button(key="run_agent").click().run()
    assert not at.exception

    # 结果出现：状态度量为「完成」
    assert "完成" in [m.value for m in at.metric]

    # 中文结果摘要与中英原因标签已渲染；英文原始输出仅放在折叠区
    assert any("首位为" in (m.value or "") for m in at.markdown)
    assert any("润滑状态退化" in (m.value or "") for m in at.markdown)

    # 工具调用表以中文列名渲染
    def _has_column(name: str) -> bool:
        for df in at.dataframe:
            value = getattr(df, "value", None)
            if isinstance(value, pd.DataFrame) and name in value.columns:
                return True
        return False

    assert _has_column("工具")

    # 成功后再提交冲突资产，旧结果必须被清除，不能与错误提示同时展示
    at.text_area(key="task_text").set_value("A002 检查最近工单。")
    at = at.button(key="run_agent").click().run()
    assert any("必须且只能引用当前资产 A001" in e.value for e in at.error)
    assert not any("首位为" in (m.value or "") for m in at.markdown)
