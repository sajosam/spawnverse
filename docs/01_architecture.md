# SpawnVerse — System Architecture

## What It Is

SpawnVerse is a self-organizing multi-agent system. Given a single task description, it invents a team of specialist AI agents at runtime, runs them in parallel according to a dependency graph, scores every output, and produces a structured final result. No agents are predefined — the LLM designs the team from scratch for each task.

---

## High-Level Run Flow

```
Orchestrator.run(task)
        │
        ▼
  1. SETUP APIs        detect which live-data helpers the task needs
        │
        ▼
  2. DECOMPOSE         LLM designs a DAG: N gathering agents + M synthesis agents
        │
        ▼
  3. DAG SCHEDULING    run waves in order; parallel within each wave
        │
        │  for each agent:
        │    ┌─────────────────────────────────────────────────┐
        │    │  route model  (UCB1 bandit picks cheapest fit)  │
        │    │  generate code  (LLM writes def main():)        │
        │    │  scan code  (guardrail layer 1)                 │
        │    │  execute  (subprocess with OS limits)           │
        │    │  validate output  (guardrail layers 3+4)        │
        │    │  score quality + drift                          │
        │    │  compute reward → update model reputation       │
        │    │  deposit fossil                                  │
        │    │  update soul                                     │
        │    └─────────────────────────────────────────────────┘
        │
        ▼
  4. SUMMARY           intent report · routing audit · stats · relationships
```

---

## Phase 1 — Task Decomposition

The orchestrator asks the LLM to plan a team as a JSON array. Each element is an agent spec:

```json
{
  "agent_id":   "ev_market_analyst",
  "role":       "Gather EV model specs and pricing from India market",
  "task":       "Find top 5 EVs under 25L INR: range, charge time, FAME-II subsidy",
  "tools_needed": ["llm_reasoning"],
  "depends_on": []
}
```

Agents with `depends_on: []` are **gathering agents** — they run immediately in parallel.
Agents with non-empty `depends_on` are **synthesis agents** — they wait for all listed agents to finish.

The plan is stored in the shared SQLite database so every subprocess can read it.

---

## Phase 2 — DAG Scheduling

The scheduler runs a `while pending:` loop:

1. Find all agents whose `depends_on` set is a subset of `completed`.
2. Run those as a wave (parallel via `ThreadPoolExecutor`).
3. Add them to `completed`, remove from `pending`.
4. Check if any running agent requested sub-spawns; score and add approved ones.
5. If `ready` is empty but `pending` is not → deadlock; raise `RuntimeError`.

```
pending  = [A, B, C, D, E, F]      # at start
completed = {}

iteration 1 → ready = [A, B, C]    # no deps → run in parallel
iteration 2 → ready = [D, E]       # depend on A, B, C → now runnable
iteration 3 → ready = [F]          # depends on D, E → now runnable
```

---

## The Agent File Structure

Every spawned agent is a Python file written to `.spawnverse_agents/<agent_id>.py`. The file has two parts that are **never mixed**:

### Part 1 — Stdlib (written by orchestrator, never by LLM)

Contains all helper functions baked in as string literals. The LLM never sees this source. Functions available to every agent:

| Function | Purpose |
|---|---|
| `read(ns, key)` | Read any namespace from SQLite |
| `read_output(aid)` | Shortcut: read another agent's `result` key |
| `read_system(key)` | Read the `system` namespace (task desc, plan, config) |
| `done_agents()` | List agent IDs that completed successfully |
| `write(key, value)` | Write to this agent's own namespace only |
| `write_result(v)` | Shortcut: write the `result` key |
| `think(prompt)` | Call the LLM, returns string |
| `think(prompt, as_json=True)` | Call the LLM, returns parsed dict |
| `send(to, type, subject, body)` | Send a message to another agent |
| `broadcast(subject, body)` | Send to all agents |
| `inbox()` | Read unread messages addressed to this agent |
| `spawn(name, role, task, tools, depth)` | Request a new sub-agent |
| `progress(pct, msg)` | Write a progress update to the DB |
| `done(score)` | Mark this agent as complete |
| `rag_search(query)` | Search the vector DB (if enabled) |
| `rag_context(query)` | Get formatted RAG context string |
| `rag_store(text)` | Store text into the vector DB |
| `vlog(kind, msg)` | Structured stdout log line |
| API helpers | `get_weather()`, `get_rate()`, `get_country()`, `get_crypto()`, `get_news()` (injected when needed) |

### Part 2 — `main()` (written by LLM)

The LLM writes only this function. It calls stdlib helpers to accomplish the agent's specific task. Rules enforced at generation time:

- No imports (everything needed is already in scope)
- No extra function definitions
- All writes go through `write_result()` / `write()` which are namespace-locked
- `think()` has a per-agent token cap (`_PABUDG`) so runaway agents can't drain the budget

Final file structure:
```
# AGENT: ev_market_analyst  depth=0  model=llama-3.1-8b-instant

<stdlib — ~200 lines of helper functions>
<api helpers — injected if external_apis is True>

def main():
    vlog('BOOT', 'starting')
    progress(0, 'boot')
    project = read_system('project')
    task_desc = project.get('description', '')
    # ... agent-specific logic ...
    write_result({'ev_data': {...}})
    progress(100, 'complete')
    done(score=0.85)

main()
```

---

## Class Map

```
Orchestrator                     orchestrator.py
  ├── DistributedMemory           memory/db.py          SQLite shared brain
  ├── VectorDB                    vectordb/store.py     ChromaDB RAG (optional)
  ├── Guardrails                  guardrails/checks.py  4-layer safety
  ├── Generator                   agents/generator.py   LLM writes main()
  ├── Executor                    agents/executor.py    subprocess runner
  ├── IntentTracker               agents/tracker.py     per-run alignment report
  ├── IntentDriftScorer           scoring/drift.py      LLM-as-judge on alignment
  ├── OutputQualityScorer         scoring/quality.py    LLM-as-judge on quality
  ├── SpawnScorer                 scoring/spawn.py      gates sub-agent requests
  ├── ComplexityScorer            routing/complexity.py skill/domain/tier inference
  ├── ModelRouter                 routing/router.py     UCB1 bandit model picker
  └── RewardEngine                routing/reward.py     reward/penalty calculation
```

---

## Config Quick Reference

| Key | Default | Effect |
|---|---|---|
| `model` | `llama-3.3-70b-versatile` | Fallback model when routing is OFF |
| `wave1_agents` | 4 | How many gathering agents the LLM should create |
| `wave2_agents` | 4 | How many synthesis agents the LLM should create |
| `parallel` | `True` | Run ready agents concurrently |
| `max_parallel` | 4 | Max threads in the pool |
| `max_depth` | 2 | Max sub-spawn depth |
| `token_budget` | 80 000 | Total tokens for the orchestrator across all LLM calls |
| `per_agent_tokens` | 8 000 | Per-agent `think()` budget (gathering) |
| `per_agent_tokens_synthesis` | 16 000 | Per-agent `think()` budget (synthesis) |
| `retry_failed` | `True` | Retry a failed agent once with a simpler prompt |
| `model_routing` | `False` | Enable UCB1 model routing |
| `external_apis` | `False` | Auto-inject live-data API helpers |
| `vector_db_enabled` | `False` | Enable ChromaDB RAG |
| `sandbox_enabled` | `True` | Apply OS resource limits (Linux/macOS only) |
| `output_format` | `"structured"` | Passed to LLM as a hint for output shape |

---

## Data Flow Between Agents

Agents communicate exclusively through the shared SQLite database. There is no direct function call or network socket between agents.

```
gathering_agent_A writes:  memory["ev_market_analyst"]["result"] = {...}
gathering_agent_B writes:  memory["forex_analyst"]["result"]     = {...}

synthesis_agent reads:
    ev_data    = read_output("ev_market_analyst")   # reads A's result
    forex_data = read_output("forex_analyst")       # reads B's result
    result     = think(f"Using: {ev_data}, {forex_data} — write the TCO model")
    write_result(result)
```

This design means:
- Agents can run in separate OS processes (no shared memory needed)
- A crashed agent doesn't bring down others
- The DB is the audit trail — every output is timestamped and persisted
