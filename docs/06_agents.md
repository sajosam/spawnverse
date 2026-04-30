# Agents — Generation, Execution, and Tracking

## The Two Types of Agent

Every run has two waves of agents, structurally different in what they're allowed to do:

| | Gathering agent | Synthesis agent |
|---|---|---|
| `depends_on` | `[]` | Non-empty list |
| When runs | Immediately (wave 1) | After all deps complete (wave 2+) |
| Token budget | `per_agent_tokens` (8 000) | `per_agent_tokens_synthesis` (16 000) |
| `think()` max tokens | 2 000 | 4 000 |
| API calls | Allowed and expected | Forbidden (all live data comes via `read_output`) |
| Prompt rules | Must use API functions for live facts | Must read upstream with `read_output`, ground every statement |

The Generator writes different system prompt rules into each type's `main()` based on the `is_synthesis` flag.

---

## Generator

**File:** `agents/generator.py`

Responsible for producing the complete `.py` file for each agent.

### Step 1 — Build the stdlib

`_build_stdlib()` produces ~200 lines of helper functions as a Python string. Key decisions made at this point:

- `_ID` is baked in — the agent cannot change its own identity
- `_MDL` is baked in — the model ID chosen by the router is hardcoded so the subprocess calls the right model
- `_PABUDG` is baked in — the per-agent token cap is enforced inside the subprocess, not by the orchestrator
- `_MAXTOK` is set to 2000 (gathering) or 4000 (synthesis) — the max token response per `think()` call
- API helper code is appended if `api_stdlib` is non-empty

### Step 2 — Build the generation prompt

The LLM prompt asks for `def main():` and nothing else. It includes:

1. **Soul hint** — if a proven pattern exists for this role (`_soul_hint()`), it's prepended as a concrete example
2. **Synthesis rules** — if `is_synthesis`, a detailed block of rules is inserted:
   - Exactly how to read each upstream dep (`read_output('dep_id') or {}`)
   - Never call API functions
   - Build `think()` prompts from real upstream values, not templates
   - Never return empty — call `think()` independently if upstream failed
3. **API hint** — if APIs are injected, exact usage patterns and explicit forbidden anti-patterns (`think('What is the weather?')` → WRONG)
4. **RAG hint** — if vector DB is enabled, how to use `rag_context()` and `rag_store()`
5. **Step-by-step template** — a concrete skeleton showing the expected flow
6. **Rules (R1–R10)** — specific code rules enforced via prompt, e.g.:
   - Never iterate directly over `read_output()` — always guard against `None`
   - Never pass more than 400 chars of upstream data into `think()`
   - Never return `{}` — always produce output

### Step 3 — Parse the LLM response

The LLM returns code with or without markdown fences. The Generator:

1. Strips ` ```python ` / ` ``` ` fences if present
2. Strips Qwen3-style `<think>...</think>` chain-of-thought blocks
3. Falls back to finding `def main(` if the think block is the entire response

### Step 4 — Assemble the final file

```python
final = (
    f"# AGENT: {agent_id}  depth={depth}  model={model_id}\n\n"
    + stdlib          # ~200 lines of helpers
    + "\n\n"
    + text            # the LLM-written main()
    + "\n\nmain()\n"  # entry point
)
```

### Retry generation

If the executor reports the agent failed (`ok=False`) and `retry_failed=True`, a second generation is triggered with a simplified prompt:

```
RETRY: Keep main() simple.
raw=read_output(x); d=raw if raw is not None else {}; d.get(k). Wrap risky in try/except.
```

The retry prompt tells the LLM to be more defensive — simpler logic, explicit None guards, try/except around everything.

---

## Executor

**File:** `agents/executor.py`

Runs the generated `.py` file as a subprocess and reports success/failure.

### Flow

```python
# 1. Code scan (guardrail layer 1)
safe, violations = guardrails.scan_code(agent_id, code, enabled=True)
if not safe:
    return False, 0.0

# 2. Write file to disk
with open(path, "w", encoding="utf-8") as f:
    f.write(code)

# 3. Configure subprocess
kwargs = {
    "capture_output": True,
    "text": True,
    "timeout": timeout,
    "env": os.environ.copy(),     # GROQ_API_KEY is inherited here
}
if os.name != "nt" and config.get("sandbox_enabled"):
    kwargs["preexec_fn"] = self._sandbox(config)  # OS resource limits

# 4. Run
result = subprocess.run([sys.executable, path], **kwargs)
```

### Timeout

Timeout is depth-dependent:

```python
timeout = config.get(f"timeout_depth{min(depth, 2)}", 60)
```

- Depth 0 (gathering): `timeout_depth0` = 120s
- Depth 1 (synthesis): `timeout_depth1` = 90s
- Depth 2+: `timeout_depth2` = 60s

Deeper agents get less time — they're expected to mostly read from already-computed upstream data, not do heavy work.

### Output handling

If `show_stdout=True`, the subprocess's stdout is printed with a divider:

```
────────────────────────────────────────────────────────────────
  ev_market_analyst  (14.3s)
────────────────────────────────────────────────────────────────
[14:30:15.123] [ev_market_analyst] BOOT
  starting

[14:30:16.841] [ev_market_analyst] PROGRESS
  0% boot
...
```

`returncode != 0` → failure. Stderr is extracted (first 600 chars) and logged.

### Sandbox

On Linux/macOS, `preexec_fn` applies three `setrlimit` calls before the subprocess starts:

- `RLIMIT_CPU` — CPU seconds (default 60)
- `RLIMIT_AS` — virtual address space in bytes (default 512 MB)
- `RLIMIT_FSIZE` — max file write size in bytes (default 10 MB)

Violations kill the subprocess with a signal; `returncode` is non-zero; the orchestrator logs a failure. This limits damage from a runaway or malicious agent even if it bypassed the code scan.

---

## Sub-Spawning

Any agent can request a new sub-agent at runtime by calling `spawn()`:

```python
spawn('price_verifier', 'Verify EV prices from a second source', 
      'Cross-check prices from ev_market_analyst with manufacturer websites', 
      ['llm_reasoning'], my_depth)
```

This writes a row to the `spawns` table. The orchestrator checks this table between every DAG iteration via `_handle_spawns()`.

### Spawn validation

The orchestrator runs each spawn request through `SpawnScorer` and applies four hard rules before approving:

| Check | Rejection reason |
|---|---|
| `depth > max_depth` | Too deep — would exceed recursion limit |
| `SpawnScorer.score() < min_spawn_score` | Heuristic score too low (vague role, no action verb, etc.) |
| `len(role) < 15` | Role too short — not a real specification |
| `len(task) < 20` | Task too short — not a real task |
| `name in existing_ids` | Duplicate — this agent already exists |

Approved spawns are appended to `pending` and enter the normal DAG scheduling loop with `depends_on=[]` (they run in the next available wave).

### SpawnScorer heuristic

Scores 0–1 based on:

| Signal | Contribution |
|---|---|
| Role length / 60 | Up to 0.15 |
| Task length / 80 | Up to 0.15 |
| No vague terms ("helper", "worker", "sub task", ...) | 0.30 |
| Has an action verb ("research", "find", "calculate", ...) | 0.20 |
| Name is unique (not a duplicate) | 0.20 |

Default `min_spawn_score = 0.4`. A spawn request needs to avoid vague terms AND have at least one signal (role length or action verb) to pass.

---

## IntentTracker

**File:** `agents/tracker.py`

Accumulates drift and quality scores for every agent in the current run and prints a formatted alignment report at the end.

### Per-agent tracking

After scoring, the orchestrator calls:

```python
self.intent.track(aid, spec["role"], drift_score, quality_score, output, wave)
```

`wave` is `"gathering"` (no deps) or `"synthesis"` (has deps).

The tracker stores a summary of what keys the output contained:

```python
# dict with keys: {'ev_models', 'charge_times', 'prices'}
→ "ev_market_analyst: [ev_models, charge_times, prices]"
```

### Intent Alignment Report

Printed after the routing audit:

```
══════════════════════════════════════════════════════════════════════
  INTENT ALIGNMENT REPORT
  Task: Research and compare top 5 electric vehicles in India
──────────────────────────────────────────────────────────────────────
  System Alignment : 0.81  ████████░░  quality=0.79

  AGENT CONTRIBUTIONS  (6 agents):
    ev_market_analyst              drift=0.92  █████████░  ✅
                                   ev_market_analyst: [ev_models, prices, ...]
    forex_analyst                  drift=0.78  ███████░░░  ✅
                                   forex_analyst: [usd_inr, eur_inr, ...]
    cost_modeller                  drift=0.35  ███░░░░░░░  🔴 WEAK
                                   cost_modeller: [cost_breakdown]

  🔴 WEAK LINKS:
    cost_modeller  drift=0.35

  CHAIN ANALYSIS:
    Gathering wave avg drift : 0.85  ████████░░
    Synthesis wave avg drift : 0.77  ███████░░░  (-0.08 vs gathering)
══════════════════════════════════════════════════════════════════════
```

**Thresholds:**
- `drift ≥ 0.65` → ✅ (aligned)
- `0.45 ≤ drift < 0.65` → ⚠️ (borderline)
- `drift < 0.45` → 🔴 WEAK (off-topic)

**Chain analysis** compares gathering vs synthesis wave averages. A synthesis wave with significantly lower drift than gathering suggests the synthesis agents drifted from the original task while processing upstream data — a useful diagnostic for prompt tuning.
