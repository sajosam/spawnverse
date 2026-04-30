# Fossil Record & Soul System

## Overview

SpawnVerse has two layers of long-term memory that survive across runs:

1. **Fossil Record** — an append-only log of every agent that has ever completed. Each entry captures what the agent did, how it was coded, and how well it performed.
2. **Soul System** — a distillation of fossils into a per-role identity. When a role accumulates enough quality fossils, its best-performing code is injected as a "proven pattern" hint at generation time, teaching the LLM from its own past work.

---

## The Fossil Record

### When a fossil is deposited

Every agent deposits a fossil at the end of its lifecycle, whether it succeeded or failed. This happens in `Orchestrator._spawn()` after scoring:

```python
self.mem.deposit_fossil(
    agent_id,
    spec["role"],
    spec["task"][:500],      # task summary
    (self.consts.get(aid) or "")[:2000],  # constitution = the generated code
    quality_score,
    drift_score,
    gen_tokens,
    elapsed,
    depth,
)
```

### What a fossil contains

| Field | Source | Description |
|---|---|---|
| `agent_id` | Runtime | The agent's unique identifier for that run |
| `role` | Agent spec | The role description (e.g. "Gather EV market data") |
| `task_summary` | Agent spec | First 500 chars of the task |
| `constitution` | Generated code | First 2000 chars of the `main()` function the LLM wrote |
| `quality` | `OutputQualityScorer` | LLM-as-judge score 0–1 on the output |
| `drift` | `IntentDriftScorer` | LLM-as-judge score 0–1 on alignment to the root task |
| `tokens` | Groq usage | Tokens used generating this agent's code |
| `runtime` | `time.time()` | Wall-clock seconds the subprocess ran |
| `depth` | Orchestrator | 0 = top-level, 1 = first sub-spawn, 2 = second sub-spawn |
| `died_at` | `datetime.now()` | Timestamp of fossil deposit |

### Database schema

```sql
CREATE TABLE fossils (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id      TEXT,
    role          TEXT,
    task_summary  TEXT,
    constitution  TEXT,
    quality       REAL DEFAULT 0.0,
    drift         REAL DEFAULT 0.0,
    tokens        INTEGER DEFAULT 0,
    runtime       REAL DEFAULT 0.0,
    depth         INTEGER DEFAULT 0,
    died_at       TEXT
);
```

Fossils are append-only. Nothing is ever deleted. Over time this table becomes a historical record of every agent that ran, what code it produced, and whether that code worked.

### What "constitution" means

The constitution is the generated `main()` function — the actual Python code the LLM wrote for that agent. It captures:
- How the agent structured its work
- Which stdlib functions it called
- How it built its `think()` prompts
- How it handled upstream data

A high-quality constitution from a previous run is concrete proof that "a certain coding pattern works for this role." The soul system extracts this and injects it into future runs.

### Vector DB integration

When `vector_db_enabled: True`, the orchestrator also indexes each agent's output into ChromaDB after the run:

```python
self.vdb.index_output(aid, spec["role"], output, spec["task"][:100])
```

This creates a semantic index over past outputs, queryable via `rag_search("forex rates India")`. Future agents can retrieve relevant past outputs as context before calling `think()`.

---

## The Soul System

### Concept

A "soul" is the persistent identity of a role across runs. Think of it as a role-level memory: "every time we need an `ev_market_analyst`, here's the code pattern that has worked best historically."

### Soul lifecycle

```
Run 1: ev_market_analyst completes, quality=0.72
       → deposit_fossil()
       → update_soul("gather ev market data...", 0.72, constitution_code)
       → souls table: total_runs=1, avg_quality=0.72, best_quality=0.72

Run 2: ev_market_analyst completes, quality=0.85
       → update_soul() → total_runs=2, avg_quality=0.785, best_quality=0.85
       → best_constitution updated (0.85 > 0.72)

Run 3: ev_market_analyst completes, quality=0.91
       → update_soul() → total_runs=3, avg_quality=0.826, best_quality=0.91
       → best_constitution updated again

Run 4: Generator._soul_hint() is called
       → get_soul(role, min_runs=3) → returns the soul
       → avg_quality=0.826 ≥ threshold=0.7 ✓
       → total_runs=3 ≥ min_runs=3 ✓
       → soul is injected into the generation prompt
```

### Soul injection

When the Generator looks up a soul before writing an agent's `main()`, it prepends a block to the LLM prompt:

```
PROVEN PATTERN (from 3 previous runs, avg_quality=0.83):
def main():
    vlog('BOOT', 'starting')
    progress(0, 'boot')
    project = read_system('project')
    task_desc = project.get('description', '') if project else ''
    ev_raw = think(f'List top 5 EVs in India under 25L INR...')
    ...
    write_result({'ev_models': ev_raw})
    done(score=0.85)
```

The LLM sees this as a guide — not a constraint — and tends to adopt the same structural patterns while adapting the content to the current task.

### Soul guardrail

Before injecting a soul constitution, it is passed through the code scanner (guardrail layer 1). If the constitution contains dangerous patterns (e.g. `subprocess.`, `eval(`, `os.system(`), the injection is blocked and logged:

```python
if guard and not guard.scan_code(agent_id, soul["best_constitution"])[0]:
    _log("SOUL", role, "INJECT_BLOCKED", "constitution failed guardrail scan", "R")
    return ""
```

This prevents a compromised constitution (e.g. from a prompt-injected past run) from propagating to future agents.

### Soul failure tracking

Failed agents also update the soul — they increment `total_runs` without updating `avg_quality` or `best_constitution`:

```python
if ok and quality_score > 0.05:
    self.mem.update_soul(spec["role"], quality_score, constitution)
elif not ok:
    self.mem.increment_soul_attempts(spec["role"])
```

This means `total_runs` reflects all attempts, so a role that fails often won't have its `avg_quality` inflated by only counting successes. The threshold check (`avg_quality >= 0.7`) naturally prevents poor-performing roles from injecting bad patterns.

### Soul database schema

```sql
CREATE TABLE souls (
    soul_id           TEXT PRIMARY KEY,   -- MD5 of role string
    role              TEXT UNIQUE NOT NULL,
    avg_quality       REAL DEFAULT 0.0,
    total_runs        INTEGER DEFAULT 0,
    best_constitution TEXT,              -- the code that achieved best_quality
    best_quality      REAL DEFAULT 0.0,
    created_at        TEXT,
    last_updated      TEXT
);
```

The `soul_id` is `MD5(role.strip().lower()[:50])` — role strings are normalized before hashing so minor wording differences don't create duplicate souls.

---

## Config Knobs

| Key | Default | Effect |
|---|---|---|
| `soul_quality_threshold` | `0.7` | Minimum `avg_quality` before soul injection fires |
| `soul_min_runs` | `3` | Minimum `total_runs` before soul injection fires |
| `soul_constitution_max_chars` | `800` | Characters of constitution injected into prompt |

### Tuning tips

- **Lower `soul_min_runs` to 2** if you want soul injection to start on the second run. Useful when iterating on a specific task type.
- **Raise `soul_quality_threshold` to 0.85** if you want only excellent patterns to propagate.
- **Raise `soul_constitution_max_chars`** if agents are complex enough that 800 chars truncates the useful part of the pattern. Watch out for prompt size limits.

---

## What This Achieves

On the first run, agents write code from scratch based on generic instructions. By run 3+, agents write code based on patterns that are proven to work for their specific role. The system bootstraps its own institutional knowledge: each run the agents get a little better at being themselves.

This is distinct from fine-tuning or RAG over documentation. The soul is derived entirely from real task performance — the LLM learning from its own successful outputs.
