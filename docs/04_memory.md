# Memory Model

## Architecture

SpawnVerse uses a single SQLite database (`spawnverse.db` by default) as the shared brain for all agents in a run. Agents are separate OS subprocesses — they cannot share Python objects in memory. The database is the only communication channel between them and the orchestrator.

SQLite is configured for concurrent access:

```python
conn.execute("PRAGMA journal_mode=WAL")     # write-ahead log: readers never block writers
conn.execute("PRAGMA synchronous=NORMAL")   # flush on checkpoint, not every write
```

WAL mode means multiple reader subprocesses can read simultaneously while one writer commits, which is the exact access pattern of a parallel agent wave.

---

## Namespace Isolation

Every key in the `memory` table is scoped to a namespace:

```sql
CREATE TABLE memory (
    namespace   TEXT,
    key         TEXT,
    value       TEXT,         -- JSON-serialized
    written_at  TEXT,
    PRIMARY KEY (namespace, key)
);
```

**The rule:** any agent can read any namespace; an agent can only write to its own namespace.

This is enforced at **two levels**:

### Level 1 — Code generation (structural)

In `_build_stdlib()`, the `write()` function is generated with `_ID` hard-coded at birth:

```python
"def write(key, value):",
"    c=_c()",
"    c.execute('INSERT OR REPLACE INTO memory VALUES (?,?,?,?)',(_ID,key,json.dumps(value),datetime.now().isoformat()))",
```

`_ID` is the agent's ID baked in as a constant. The function has no `namespace` parameter. It is structurally impossible for the generated `main()` to write to another agent's namespace — the parameter doesn't exist.

### Level 2 — DB layer (runtime check)

`DistributedMemory.write()` has an optional `caller_id` parameter that the orchestrator passes when writing on behalf of agents:

```python
def write(self, owner: str, key: str, value, caller_id: str = None) -> bool:
    if caller_id and caller_id != owner:
        _log("MEM", owner, "WRITE_REJECTED", f"'{caller_id}' tried to write to '{owner}'", "R")
        return False
```

---

## Namespaces

| Namespace | Writer | Contents |
|---|---|---|
| `system` | Orchestrator | `project` (task + context), `plan` (agent DAG), `task_desc` |
| `<agent_id>` | That agent only | `result` (final output), any intermediate keys |
| `_cache_` | API helpers | Cached API responses (weather, forex, etc.), TTL 120s |

### Reading patterns

```python
# Read the root task description
project   = read_system('project')
task_desc = project.get('description', '')

# Read another agent's output (works from inside any agent)
ev_data = read_output('ev_market_analyst')   # returns None if not ready

# Always guard against None
raw   = read_output('forex_analyst')
rates = raw if isinstance(raw, dict) else {}
```

---

## All Tables

### `agents`

The lifecycle register. One row per agent per run.

```sql
CREATE TABLE agents (
    agent_id    TEXT PRIMARY KEY,
    role        TEXT,
    status      TEXT DEFAULT 'spawning',   -- running | done | failed
    depth       INTEGER DEFAULT 0,
    spawned_by  TEXT,
    started_at  TEXT,
    ended_at    TEXT,
    quality     REAL DEFAULT 0.0,
    drift       REAL DEFAULT 0.0,
    tokens      INTEGER DEFAULT 0,
    success     INTEGER DEFAULT 0,          -- 0 or 1
    model_id    TEXT DEFAULT NULL,
    skill       TEXT DEFAULT NULL,
    domain      TEXT DEFAULT NULL,
    run_id      TEXT DEFAULT NULL
);
```

### `messages`

Inter-agent message bus. Append-only.

```sql
CREATE TABLE messages (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    from_agent  TEXT,
    to_agent    TEXT,     -- specific agent_id or 'ALL' for broadcast
    msg_type    TEXT,
    subject     TEXT,
    body        TEXT,     -- JSON
    read        INTEGER DEFAULT 0,
    sent_at     TEXT
);
```

Agents call `send(to, type, subject, body)` and `broadcast(subject, body)`. Messages sent to `'ALL'` are visible to every agent that calls `inbox()`. The `read` flag is set per-reader to 1 when consumed.

### `spawns`

Sub-agent request queue. Agents write to this; the orchestrator reads it between DAG iterations.

```sql
CREATE TABLE spawns (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    requested_by TEXT,
    depth        INTEGER,
    name         TEXT,       -- requested agent_id
    role         TEXT,
    task         TEXT,
    tools        TEXT,       -- JSON array
    score        REAL DEFAULT 0.0,
    status       TEXT DEFAULT 'pending',   -- pending | done | rejected
    requested_at TEXT
);
```

After each DAG wave completes, the orchestrator calls `mem.pending_spawns()` and runs each request through `SpawnScorer`. Approved requests are added to `pending`; rejected ones are marked `rejected`.

### `fossils`

Permanent historical record. See `docs/03_fossil_record.md` for full details.

### `progress`

Agent progress updates. Append-only per agent.

```sql
CREATE TABLE progress (
    agent_id TEXT,
    pct      INTEGER,
    message  TEXT,
    ts       TEXT
);
```

Agents call `progress(50, 'halfway done')` which both writes here and prints a colored bar to stdout.

### `relationships`

Tracks which agents co-occurred in the same run and how their quality scores compared.

```sql
CREATE TABLE relationships (
    agent_a     TEXT,
    agent_b     TEXT,
    run_id      TEXT,
    score_a     REAL DEFAULT 0.0,
    score_b     REAL DEFAULT 0.0,
    recorded_at TEXT,
    PRIMARY KEY (agent_a, agent_b, run_id)
);
```

After each agent completes, the orchestrator records its quality against every already-completed agent in the same run. `strong_relationships()` queries pairs that consistently achieve high combined quality, surfacing which agent roles tend to work well together.

### `guardrail_log`

Audit trail for every guardrail block event.

```sql
CREATE TABLE guardrail_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id  TEXT,
    layer     TEXT,      -- code_scan | output | semantic
    verdict   TEXT,      -- blocked
    detail    TEXT,
    ts        TEXT
);
```

### `intent_log`

Per-agent alignment scores for the current run. See `docs/06_scoring.md`.

```sql
CREATE TABLE intent_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT,
    agent_id    TEXT,
    role        TEXT,
    drift       REAL DEFAULT 0.0,
    quality     REAL DEFAULT 0.0,
    contribution TEXT,
    wave        TEXT DEFAULT 'gathering',   -- gathering | synthesis
    ts          TEXT
);
```

### `souls`

Per-role persistent identity. See `docs/03_fossil_record.md` for full details.

### `model_reputation`

Per-model learned performance. See `docs/02_model_routing.md` for full details.

---

## API Response Cache

The `_cache_` namespace in the `memory` table doubles as a short-lived API cache. API helper functions (`get_weather`, `get_rate`, etc.) check this before hitting the network:

```python
def _api_cache_get(key, max_age=120):
    row = c.execute("SELECT value, stored_at FROM memory WHERE namespace='_cache_' AND key=?", (key,))
    if row:
        age = (datetime.now() - datetime.fromisoformat(row[1])).total_seconds()
        if age < max_age:
            return json.loads(row[0])
    return None
```

TTL is 120 seconds. This means parallel agents running in the same wave won't hammer the same endpoint — the first one fetches and caches, the rest read from SQLite. After 120 seconds the cache entry is stale and the next agent refetches.

---

## Run Isolation

Each `Orchestrator.run()` call has a `run_id` (timestamp-based, e.g. `20250430_143022`). The `agents` table stores `run_id` so that `all_outputs(run_id=...)` returns only results from the current run, not previous runs stored in the same DB.

This is important when reusing a DB across multiple runs (the default): SQLite accumulates all runs but queries are scoped to the current `run_id`.

The examples delete and recreate the DB file between runs for a clean slate:

```python
if os.path.exists(CONFIG["db_path"]):
    os.remove(CONFIG["db_path"])
```

But the soul and reputation tables are kept if you want the system to learn across runs — delete only the operational tables, not those.

---

## Concurrency Safety

Multiple agent subprocesses write to the same SQLite file concurrently. WAL mode handles this safely:

- **Readers** never block, even during a write commit
- **Writers** serialize at the DB level (SQLite's WAL allows one writer at a time)
- `timeout=20` on every connection means a blocked writer waits up to 20 seconds before raising `OperationalError`

The orchestrator's main thread also writes (registering agents, depositing fossils, updating reputations) while subprocesses run. WAL + the 20s timeout makes this safe without explicit locking in Python code.
