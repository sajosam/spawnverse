# Scoring

## Overview

Three independent scorers run per agent after a successful execution. Each returns a float 0–1 with a distinct meaning:

| Scorer | Question answered | Method |
|---|---|---|
| `OutputQualityScorer` | Is this output good? | LLM-as-judge |
| `IntentDriftScorer` | Does this output address the root task? | LLM-as-judge |
| `SpawnScorer` | Is this sub-agent request worth creating? | Heuristic only |

Quality and drift are computed after the subprocess completes. Spawn score is computed by the orchestrator when processing spawn requests between DAG waves.

---

## OutputQualityScorer

**File:** `scoring/quality.py`

### What it measures

Independent quality of the agent's output, evaluated against that agent's specific task. A quality of 1.0 means the output is an excellent, specific answer to the agent's task. A quality of 0.0 means the output is empty, wrong domain, or meaningless.

### Fast path

Before making an LLM call, the scorer checks for known failure signatures:

```python
_USELESS_PHRASES = [
    "no context", "no relevant", "no data", "not available",
    "unable to", "insufficient data", "no information",
]

output_str = str(output).lower()
if len(output_str) < 100 and any(p in output_str for p in _USELESS_PHRASES):
    return 0.05
```

Short outputs containing apologetic phrases are immediately scored 0.05 without calling the LLM. This saves tokens for the common case of an agent that failed silently.

### LLM prompt

```
Score output quality 0.0-1.0.
TASK: <task[:150]>
OUTPUT: <str(output)[:300]>
1.0=excellent specific answer. 0.0=empty or wrong domain.
Return ONLY: {"score": 0.X}
```

Max 80 tokens. The LLM returns a JSON object; the scorer parses it and clamps to [0.0, 1.0].

### Failure default

If the LLM call fails or returns unparseable JSON, the score defaults to `0.0` (not 0.5). A scoring failure is treated as a negative signal, not a neutral one.

---

## IntentDriftScorer

**File:** `scoring/drift.py`

### What it measures

How well the agent's output addresses the **root task** (the top-level task description), not just its individual sub-task. This distinguishes between "the agent did its local job well" (quality) and "the agent's work is relevant to what the user actually asked for" (drift).

Example: if the root task is "research EVs in India under 25L INR" and a synthesis agent produces a detailed report about European EV markets, its quality score might be high but its drift score will be near 0 — it produced good content that isn't what was asked for.

### Edge case

Empty output returns 0.5 (neutral):

```python
if not output or (isinstance(output, dict) and not any(output.values())):
    return 0.5
```

An empty output doesn't produce a drift penalty — it's penalized by quality scoring instead. This avoids double-penalizing failed agents.

### LLM prompt

```
Score 0.0-1.0: does this output address the task?
TASK: <root task[:150]>
ROLE: <agent role>
OUTPUT (first 600 chars): <str(output)[:600]>
1.0=excellent relevant content. 0.0=empty or completely wrong domain.
Data-gathering agents (weather, rates, country data, prices, news) score 0.7-1.0
when the data they return is relevant to the task domain.
Return ONLY: {"score": 0.X}
```

The special instruction for gathering agents ("score 0.7-1.0 when relevant to the task domain") prevents the LLM from penalizing weather or forex agents for not producing a full analysis — their job is to fetch data, not synthesize it, so a correct forex rate for an EV task should score high.

### Failure default

If scoring fails, returns `0.5` (neutral). Unlike quality, drift failure is neutral because drift failure is more likely to be a scoring infrastructure problem than an indication that the agent misbehaved.

---

## How Quality and Drift Work Together

The two scores are used in three places:

### 1. Output acceptance

If `quality < quality_min (0.45)` or `drift < drift_warn (0.45)`, the final output display adds a warning flag:

```python
flag = " ⚠️" if (q < self.cfg["quality_min"] or d < self.cfg["drift_warn"]) else ""
```

The output is still included in the result — it's a warning, not a rejection. Guardrail layers 3 and 4 are the true rejection mechanisms.

### 2. Reward computation

Both scores feed directly into the reward signal for model routing:

```
success: reward = drift × quality × reward_mult
failure: penalty = -(gap × penalty_mult)
```

An agent that scores high on both earns a large positive reward for its chosen model. An agent that scores low on either (or both) earns a penalty. See `docs/02_model_routing.md` for the full reward logic.

### 3. Soul update

```python
if ok and quality_score > 0.05:
    self.mem.update_soul(spec["role"], quality_score, constitution)
```

Quality determines whether the run contributes to the soul and how much weight it carries. Drift is not directly used in soul accumulation — a high-drift, high-quality run that happened to be off-topic still contributes its constitution as a quality signal for how to write code for that role.

---

## SpawnScorer

**File:** `scoring/spawn.py`

### What it measures

Whether a sub-agent spawn request is worth creating. Unlike the other two scorers, this is a heuristic with no LLM call.

### Scoring signals

| Signal | Score contribution | Rationale |
|---|---|---|
| Role length / 60 | Up to 0.15 | Longer role = more specific = more likely to be useful |
| Task length / 80 | Up to 0.15 | Same reasoning |
| No vague terms | 0.30 | The biggest single factor |
| Has action verb | 0.20 | Confirms the agent will actually do something |
| Unique name | 0.20 | Prevents duplicate agents |

**Vague terms** that kill the score: `"sub role"`, `"helper"`, `"assistant"`, `"worker"`, `"sub agent"`, `"do work"`, `"complete task"`, `"perform task"`, `"generate report"`

**Action verbs** that boost the score: `"research"`, `"find"`, `"calculate"`, `"compare"`, `"summarise"`, `"validate"`, `"extract"`, `"compile"`, `"recommend"`, `"estimate"`, `"verify"`, `"draft"`, `"synthesize"`, and more

### Why the design

LLMs sometimes generate spawn requests as vague catch-all agents ("helper", "processor") instead of specific work. The heuristic is designed to aggressively reject these without an LLM call. A score below `min_spawn_score (0.4)` — which is achievable just by avoiding vague terms and having at least one signal — means the request is rejected before it ever enters the DAG.

The orchestrator also applies hard structural checks on top of the score (depth limit, minimum role/task length, duplicate detection). SpawnScorer provides the quality signal; the hard checks provide the safety rails.

---

## Score Summary in Execution Output

Both quality and drift appear in multiple places in the output:

```
──────────────────────────────────────────────────────────────────────
  EV MARKET ANALYST
  quality=0.82  drift=0.91  model=llama-3.1-8b-instant  skill=extract
──────────────────────────────────────────────────────────────────────

══════════════════════════════════════════════════════════════════════
  EXECUTION SUMMARY
──────────────────────────────────────────────────────────────────────
  Agents         : 6 (5 ok, 1 failed)
  Quality / Drift: 0.79 / 0.83
```

And in the routing audit:

```
  AGENT                        MODEL          SKILL      Q      D    REWARD
  ev_market_analyst            llama-3.1-8b   extract  0.82   0.91  +1.023  ✅
```

The routing audit is the definitive record of how each score translated into a reward signal for the model bandit.
