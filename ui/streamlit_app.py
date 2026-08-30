"""Streamlit UI: Agent, Asset Explorer, and Trace Inspector."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from src.agent import policy
from src.agent.runner import AgentRunner
from src.db.repository import Repository

st.set_page_config(page_title="Industrial Maintenance Agent", layout="wide")


@st.cache_resource
def get_runner() -> AgentRunner:
    return AgentRunner(Repository(ROOT / "data" / "industrial.db"), ROOT / "traces")


runner = get_runner()

tab_agent, tab_assets, tab_traces = st.tabs(
    ["Agent", "Asset Explorer", "Trace Inspector"]
)

with tab_agent:
    st.subheader("Agent")
    question = st.text_input(
        "Question",
        value="A001 stopped this week. Check recent work orders, meter trend and docs.",
    )

    if "agent_state" not in st.session_state:
        st.session_state.agent_state = None

    if st.button("Run agent", key="run_agent"):
        st.session_state.agent_state = runner.run(question)

    state = st.session_state.agent_state

    if state is not None and state.pending_action is not None:
        st.caption(
            "Approving or rejecting records a decision only; in v0 no external "
            "action is executed."
        )
        col_a, col_r = st.columns(2)
        if col_a.button("Approve", key="approve"):
            st.session_state.agent_state = policy.approve(state, "streamlit-user")
            state = st.session_state.agent_state
            st.success("Approved")
        if col_r.button("Reject", key="reject"):
            st.session_state.agent_state = policy.reject(state, "streamlit-user")
            state = st.session_state.agent_state
            st.info("Rejected")

    if state is None:
        st.info("Run the agent to see results.")
    else:
        st.markdown(state.final_answer or "(no answer)")
        with st.expander("Hypotheses"):
            st.json([h.model_dump() for h in state.hypotheses])
        with st.expander("Evidence"):
            st.json([e.model_dump() for e in state.evidence])
        if state.pending_action is not None:
            st.json(state.pending_action.model_dump())

with tab_assets:
    st.subheader("Asset Explorer")
    asset_id = st.text_input("Asset ID", value="A001")
    if st.button("Load asset", key="load_asset"):
        asset = runner.repo.get_asset(asset_id)
        if asset is None:
            st.warning("Asset not found")
        else:
            st.json(asset.model_dump())
            orders = runner.repo.search_recent_work_orders(asset_id, 30, 20)
            st.dataframe([o.model_dump() for o in orders])

with tab_traces:
    st.subheader("Trace Inspector")
    request_ids = runner.traces.list()
    if request_ids:
        selected = st.selectbox("Request", request_ids)
        if selected:
            st.json(runner.traces.load(selected).model_dump())
    else:
        st.info("No traces yet.")
