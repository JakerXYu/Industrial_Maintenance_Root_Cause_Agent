## 13A. Seven-Agent Delegation Policy

The default primary agent (`code`, using GPT-5.6 Sol) is the **Lead Engineer**. It owns requirement interpretation, decomposition, architecture decisions, prioritization, conflict resolution, final acceptance, and final synthesis.

### `gpt-architect` — high-value architecture judgment
Use for cross-module design, API/schema/interface decisions, major refactors, migration planning, and long-lived trade-offs. Prefer after `ds-explorer` has gathered evidence and before `ds-worker` implements significant changes. Do not use it for broad repository exploration or routine coding.

### `gpt-critic` — independent second opinion
Use for significant plans, ambiguous/high-impact decisions, conflicting specialist evidence, and important final acceptance. Its job is to challenge assumptions, identify evidence gaps, test simpler alternatives, and issue an independent verdict. It is not a replacement for routine `ds-reviewer` code review.

### `ds-explorer` — broad evidence gathering
Use for repository-wide search, locating implementations, call/dependency tracing, and token-heavy read-only investigation.

### `ds-debugger` — runtime/root-cause investigation
Use for failing tests, logs, stack traces, reproduction, diagnostics, and competing root-cause hypotheses.

### `ds-worker` — bounded implementation
Use only after the implementation direction is sufficiently clear. Handles targeted fixes, bounded features, repetitive refactors, tests, and validation loops.

### `ds-reviewer` — routine independent technical review
Use for repository audits and post-change review of correctness, tests, regressions, maintainability, and security. For strategically important or disputed conclusions, escalate to `gpt-critic`.

### Default high-value workflow
For significant implementation work, prefer:

`Lead → ds-explorer → gpt-architect → Lead decision → ds-worker → ds-debugger (if needed) → ds-reviewer → gpt-critic (for important changes) → Lead final acceptance`

Rules:
- Do not delegate merely to delegate.
- Keep mechanical/token-heavy work on DeepSeek specialists.
- Spend GPT-5.6 Sol on judgment, architecture, disagreement resolution, and acceptance.
- The Lead must evaluate evidence rather than copy specialist conclusions.
- Do not use `ds-worker` for read-only tasks.
- Use `gpt-critic` selectively for high-impact work; routine changes usually need only `ds-reviewer`.
