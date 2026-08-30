"""State-machine runner: interpret -> plan -> execute -> synthesize -> trace."""

import time
import uuid
from pathlib import Path
from typing import Optional

from src.agent import executor, planner, policy, synthesizer, tracing
from src.agent.request_id import validate_request_id
from src.agent.tools import ToolRegistry
from src.contracts import AgentState
from src.db.repository import Repository
from src.rag.chunking import load_documents
from src.rag.retriever import KeywordRetriever

ROOT = Path(__file__).resolve().parents[2]


class AgentRunner:
    def __init__(self, repo: Repository, traces_dir: Path):
        self.repo = repo
        chunks = load_documents(ROOT / "data" / "docs")
        self.registry = ToolRegistry(repo, KeywordRetriever(chunks))
        self.traces = tracing.TraceStore(traces_dir)

    def run(self, question: str, request_id: Optional[str] = None) -> AgentState:
        request_id = uuid.uuid4().hex if request_id is None else request_id
        validate_request_id(request_id)
        state = AgentState(request_id=request_id, user_question=question)
        started = time.perf_counter()
        try:
            planner.interpret(state, self.repo)
            plan = planner.plan(state)
            if state.status.value not in ("error",):
                meter_readings = executor.execute(state, self.registry, plan)
                synthesizer.synthesize(state, meter_readings, self.repo)
        except Exception as exc:  # degrade gracefully; do not crash the harness
            from src.contracts import AgentStatus

            state.status = AgentStatus.ERROR
            state.final_answer = f"agent failed: {exc}"
        total_latency_ms = int((time.perf_counter() - started) * 1000)
        self.traces.save(tracing.to_trace_record(state, total_latency_ms))
        return state
