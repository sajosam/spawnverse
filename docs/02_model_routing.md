# Model Routing

## Why It Exists

Without routing, every agent uses the same model regardless of what it actually needs to do. A simple "fetch the USD/INR rate and format it" agent gets the same expensive 70B model as a complex "synthesize a full investment thesis across 5 data sources" agent. That wastes money and saturates rate limits.

Model routing assigns the cheapest model that can handle each specific agent — and it learns over time which models work best for which task types.

---

## The Three-Stage Pipeline

```
Agent spec (agent_id, role, task, depends_on)
          │
          ▼
  1. ComplexityScorer
     → complexity: float 0–1
     → skill: "summarize" | "extract" | "reason" | "synthesize" | ...
     → domain: "finance" | "travel" | "code" | "general" | ...
          │
          ▼
  2. ModelRouter  (UCB1 bandit)
     reads: model_reputation table (domain, skill)
     picks: cheapest model with highest UCB score
     → model_id: e.g. "llama-3.1-8b-instant"
          │
          ▼
  3. Agent runs → quality score + drift score computed
          │
          ▼
  4. RewardEngine
     → reward: float (positive = good, negative = bad)
          │
          ▼
  5. model_reputation table updated
     (feeds back into step 2 for the next run)
```

---

## Stage 1 — ComplexityScorer

**File:** `routing/complexity.py`

Zero LLM calls. Pure heuristic from the agent spec dict.

### Signals and weights

| Signal | How measured | Max contribution |
|---|---|---|
| Task word count | `len(task.split()) / 60` | 0.20 |
| Upstream dependency count | `len(depends_on) × 0.15` | 0.30 |
| Verb type in role/task | synthesis verb → +0.30, gathering verb → +0.05 | 0.30 |
| Spawn depth | `depth × 0.10` | unlimited (capped at 1.0 total) |

**Synthesis verbs** (score high): synthesize, combine, merge, evaluate, recommend, rank, compare, plan, write report, final  
**Gathering verbs** (score low): fetch, get, retrieve, find, search, collect, extract, scrape

A dependency count of 2+ combined with synthesis verbs easily pushes complexity above 0.65 (tier 4+), which is correct — synthesis agents genuinely need a stronger model.

### Skill detection

Keyword matching against `SKILL_KEYWORDS` in `config.py`. Whichever skill category has the most keyword hits wins:

```
"summarize" → ["summarize", "summary", "condense", "brief", "recap", ...]
"extract"   → ["extract", "parse", "pull out", "retrieve", "scrape", ...]
"reason"    → ["reason", "infer", "analyse", "evaluate", "compare", ...]
"code"      → ["code", "script", "function", "implement", "build", ...]
"synthesize"→ ["synthesize", "synthesis", "combine", "merge", ...]
"plan"      → ["plan", "itinerary", "schedule", "roadmap", "strategy", ...]
"research"  → ["research", "investigate", "study", "explore", "survey", ...]
"classify"  → ["classify", "categorize", "label", "tag", ...]
"format"    → ["format", "template", "structure", "convert", "render", ...]
```

**Override:** If an agent has `depends_on` but was classified as `"extract"` (because "gather" appeared in its task text), the scorer overrides this to `"synthesize"` — a dependency-having agent is doing synthesis, not data extraction.

### Tier floor

Complexity maps to a minimum model tier:

| Complexity | Tier floor | Example models |
|---|---|---|
| < 0.25 | 1 | llama-3.1-8b-instant |
| 0.25–0.45 | 2 | groq/compound-mini |
| 0.45–0.65 | 3 | llama-4-scout-17b |
| 0.65–0.80 | 4 | qwen/qwen3-32b |
| ≥ 0.80 | 5 | llama-3.3-70b-versatile |

If `external_apis` is enabled, the floor is raised to at least tier 2 because tier 1 (8B) cannot reliably follow the injected API instructions.

---

## Stage 2 — ModelRouter (UCB1 Bandit)

**File:** `routing/router.py`

The router solves the **explore vs exploit** tradeoff: try new models (explore) to discover which are best, but also use known-good models (exploit) to keep quality high.

### UCB1 formula

```
UCB(model) = avg_reward × skill_prior  +  C × √( ln(N_total) / n_model )
```

| Variable | Meaning |
|---|---|
| `avg_reward` | Cumulative average reward this model has earned for this (domain, skill) pair |
| `skill_prior` | The model's declared skill score from `MODEL_REGISTRY` (0–1) |
| `C` | Exploration constant, default `1.2` (`routing_explore_c` config) |
| `N_total` | Total agent runs across all models for this (domain, skill) |
| `n_model` | Runs this specific model has done for this (domain, skill) |

**The exploration term `C × √(ln N_total / n_model)`:**
- When `n_model` is small (new/unexplored model), this term is large → model gets a high UCB score and gets selected more.
- As `n_model` grows, the term shrinks → model must prove itself on `avg_reward` alone.
- As `N_total` grows logarithmically, even explored models get occasional re-exploration.

### Cold start problem

When `n_model = 0` (a model has never been used for this skill/domain), the formula divides by zero. SpawnVerse solves this by using the model's declared `skill_prior` as a seed:

```python
if n_m == 0:
    ucb = skill_prior + C × √(ln(N_total + 1))
```

This means unvisited models are explored proportionally to their declared strength, not all given the same infinite bonus. A model declared weak at "code" (prior = 0.25) won't blindly be picked for a code task just because it's unexplored.

### Candidate filtering (before UCB)

Before running UCB, the router eliminates unsuitable models:

1. **Context window check:** `model.context_window >= token_estimate × safety_mult`  
   Token estimate = `len(task.split()) × 4` (rough word-to-token ratio).  
   `safety_mult` defaults to 3 to leave headroom for the stdlib + prompt overhead.

2. **Blacklist:** Models in `agent_model_blacklist` are excluded. Default blacklist: `["groq/compound", "llama-3.1-70b-versatile", "deepseek-r1-distill-llama-70b"]`.  
   `groq/compound` is blacklisted because it causes 413 (request too large) errors on agent-sized prompts.

3. **Tier floor:** Only models at or above the tier computed by `ComplexityScorer.tier_floor()` are considered.

If filtering removes all candidates, the constraint is relaxed (tier floor dropped, then blacklist relaxed as a last resort).

### Model Registry

Six models defined in `config.py`, each with:
- **tier:** 1 (cheapest/weakest) → 5 (most capable/expensive)
- **context_window:** Token limit
- **cost_input_per_1k / cost_output_per_1k:** For reference (not used in routing math directly)
- **reward_mult:** Multiplier applied to successful run rewards — cheaper models have higher multipliers (1.5 for tier 1 vs 0.7 for tier 5) so a successful cheap model earns disproportionately large rewards, training the bandit to prefer it
- **penalty_mult:** Multiplier on failures — cheaper models have higher penalty_mult too, so sloppy cheap-model failures get penalized more
- **skills:** Dict of skill → declared capability score (0–1)

| Model | Tier | Best skills |
|---|---|---|
| llama-3.1-8b-instant | 1 | summarize (0.88), classify (0.82) |
| groq/compound-mini | 2 | classify (0.85), extract (0.82) |
| llama-4-scout-17b-16e | 3 | code (0.78), reason (0.75) |
| qwen/qwen3-32b | 4 | reason (0.88), code (0.85), synthesize (0.82) |
| groq/compound | 5 | reason (0.92), synthesize (0.90) — blacklisted |
| llama-3.3-70b-versatile | 5 | reason (1.00), synthesize (0.95), research (0.92) |

---

## Stage 3 — RewardEngine

**File:** `routing/reward.py`

After each agent run, a reward (positive) or penalty (negative) is computed and written to the `model_reputation` table.

### Success reward (drift ≥ threshold AND quality ≥ min)

```
reward = drift × quality × reward_mult
```

For `extract` and `format` skill agents, quality is the primary signal (these agents fetch data, not reason — drift alone isn't a sufficient judge). Special case: if `drift < 0.1` even for a data agent, it's penalized because the data was completely off-topic.

### Failure penalty

```
gap    = max(thresh - drift, q_min - quality)   # whichever fell short more
penalty = -(gap × penalty_mult)
```

### Why cheap models earn more per success

| Model | `reward_mult` | Successful run reward (drift=0.9, quality=0.8) |
|---|---|---|
| llama-3.1-8b-instant | 1.5 | 0.9 × 0.8 × 1.5 = **1.08** |
| qwen/qwen3-32b | 0.9 | 0.9 × 0.8 × 0.9 = **0.648** |
| llama-3.3-70b-versatile | 0.7 | 0.9 × 0.8 × 0.7 = **0.504** |

The bandit learns: "use the 8B model for summarization — when it works, the reward is huge."

---

## Reputation Persistence

Model reputation lives in the `model_reputation` SQLite table, scoped by `(model_id, domain, skill)`:

```sql
CREATE TABLE model_reputation (
    model_id     TEXT,
    domain       TEXT,
    skill        TEXT,
    total_runs   INTEGER,
    total_reward REAL,
    avg_reward   REAL,
    last_updated TEXT,
    PRIMARY KEY (model_id, domain, skill)
);
```

`avg_reward` is updated with a running mean after every agent completion. This persists across runs — the bandit's knowledge compounds over time.

**Example reputation after 10 runs:**
```
MODEL                          DOMAIN    SKILL       RUNS  AVG_REWARD
llama-3.1-8b-instant           finance   summarize      4      +0.82
llama-3.3-70b-versatile        finance   synthesize     3      +0.61
qwen/qwen3-32b                 finance   reason         3      +0.55
```

After 30+ runs, gathering tasks are almost always assigned to the 8B model, synthesis to the 70B — for a fraction of the cost.

---

## Routing Audit Output

At the end of every run, the orchestrator prints a routing audit table:

```
══════════════════════════════════════════════════════════════════════
  MODEL ROUTING AUDIT
──────────────────────────────────────────────────────────────────────
  AGENT                        MODEL          SKILL           Q     D   REWARD
  ev_market_analyst            llama-3.1-8b   extract      0.82  0.88  +0.985  ✅
  forex_analyst                llama-3.1-8b   extract      0.79  0.91  +0.948  ✅
  financial_modeller           qwen3-32b      code         0.71  0.76  +0.511  ✅
  investment_thesis            llama-3.3-70b  synthesize   0.88  0.92  +0.565  ✅
──────────────────────────────────────────────────────────────────────
                                          Total reward:        +3.009
```

---

## Config Knobs

| Key | Default | Effect |
|---|---|---|
| `model_routing` | `False` | Master switch — disabled means all agents use `model` |
| `routing_explore_c` | `1.2` | UCB exploration constant — higher = more exploration |
| `drift_threshold` | `0.65` | Minimum drift score to count as a successful run |
| `routing_tier_floor_enabled` | `True` | Enforce minimum tier per complexity score |
| `routing_context_safety_mult` | `3` | Context window safety buffer (token_estimate × this) |
| `agent_model_blacklist` | `["groq/compound", ...]` | Models never assigned to agents |
