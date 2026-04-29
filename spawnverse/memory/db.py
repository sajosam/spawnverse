# spawnverse/memory/db.py
import os
import json
import sqlite3
import hashlib
from datetime import datetime

from ..display import _log


class DistributedMemory:
    """
    Shared SQLite store with enforced namespace isolation.

    READ  → any agent can read any namespace
    WRITE → agents may only write to their own namespace

    WAL mode + NORMAL sync keeps concurrent subprocess writes safe
    without full serialisation.
    """

    def __init__(self, config: dict) -> None:
        self.cfg = config
        os.makedirs(config["agents_dir"], exist_ok=True)
        self._init_schema()

    # ── connection ────────────────────────────────────────────────────

    def _conn(self) -> sqlite3.Connection:
        path = self.cfg["db_path"]
        conn = (sqlite3.connect(path, uri=True, timeout=20)
                if path.startswith("file:") or path == ":memory:"
                else sqlite3.connect(path, timeout=20))
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def _init_schema(self) -> None:
        with self._conn() as c:
            c.executescript("""
                CREATE TABLE IF NOT EXISTS memory (
                    namespace TEXT, key TEXT, value TEXT,
                    written_at TEXT, PRIMARY KEY(namespace, key));

                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_agent TEXT, to_agent TEXT, msg_type TEXT,
                    subject TEXT, body TEXT,
                    read INTEGER DEFAULT 0, sent_at TEXT);

                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY, role TEXT,
                    status TEXT DEFAULT 'spawning',
                    depth INTEGER DEFAULT 0, spawned_by TEXT,
                    started_at TEXT, ended_at TEXT,
                    quality REAL DEFAULT 0.0, drift REAL DEFAULT 0.0,
                    tokens INTEGER DEFAULT 0, success INTEGER DEFAULT 0,
                    model_id TEXT DEFAULT NULL,
                    skill TEXT DEFAULT NULL,
                    domain TEXT DEFAULT NULL,
                    run_id TEXT DEFAULT NULL);

                CREATE TABLE IF NOT EXISTS spawns (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    requested_by TEXT, depth INTEGER,
                    name TEXT, role TEXT, task TEXT, tools TEXT,
                    score REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'pending', requested_at TEXT);

                CREATE TABLE IF NOT EXISTS fossils (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT, role TEXT, task_summary TEXT,
                    constitution TEXT,
                    quality REAL DEFAULT 0.0, drift REAL DEFAULT 0.0,
                    tokens INTEGER DEFAULT 0, runtime REAL DEFAULT 0.0,
                    depth INTEGER DEFAULT 0, died_at TEXT);

                CREATE TABLE IF NOT EXISTS progress (
                    agent_id TEXT, pct INTEGER, message TEXT, ts TEXT);

                CREATE TABLE IF NOT EXISTS relationships (
                    agent_a TEXT, agent_b TEXT, run_id TEXT,
                    score_a REAL DEFAULT 0.0, score_b REAL DEFAULT 0.0,
                    recorded_at TEXT,
                    PRIMARY KEY(agent_a, agent_b, run_id));

                CREATE TABLE IF NOT EXISTS guardrail_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT, layer TEXT,
                    verdict TEXT, detail TEXT, ts TEXT);

                CREATE TABLE IF NOT EXISTS intent_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT, agent_id TEXT, role TEXT,
                    drift REAL DEFAULT 0.0, quality REAL DEFAULT 0.0,
                    contribution TEXT, wave TEXT DEFAULT 'gathering', ts TEXT);

                CREATE TABLE IF NOT EXISTS souls (
                    soul_id TEXT PRIMARY KEY,
                    role TEXT UNIQUE NOT NULL,
                    avg_quality REAL DEFAULT 0.0,
                    total_runs INTEGER DEFAULT 0,
                    best_constitution TEXT,
                    best_quality REAL DEFAULT 0.0,
                    created_at TEXT, last_updated TEXT);

                CREATE TABLE IF NOT EXISTS model_reputation (
                    model_id  TEXT,
                    domain    TEXT,
                    skill     TEXT,
                    total_runs   INTEGER DEFAULT 0,
                    total_reward REAL    DEFAULT 0.0,
                    avg_reward   REAL    DEFAULT 0.0,
                    last_updated TEXT,
                    PRIMARY KEY (model_id, domain, skill));
            """)

    # ── model reputation ──────────────────────────────────────────────

    def get_model_reputation(self, domain: str, skill: str) -> dict:
        with self._conn() as c:
            rows = c.execute(
                "SELECT model_id, total_runs, avg_reward "
                "FROM model_reputation WHERE domain=? AND skill=?",
                (domain, skill),
            ).fetchall()
        return {r[0]: {"total_runs": r[1], "avg_reward": r[2]} for r in rows}

    def update_model_reputation(self, model_id: str, domain: str, skill: str, reward: float) -> None:
        now = datetime.now().isoformat()
        with self._conn() as c:
            c.execute("""
                INSERT INTO model_reputation
                    (model_id, domain, skill, total_runs, total_reward, avg_reward, last_updated)
                VALUES (?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(model_id, domain, skill) DO UPDATE SET
                    total_runs   = model_reputation.total_runs + 1,
                    total_reward = model_reputation.total_reward + excluded.total_reward,
                    avg_reward   = (model_reputation.total_reward + excluded.total_reward)
                                   / (model_reputation.total_runs + 1),
                    last_updated = excluded.last_updated
            """, (model_id, domain, skill, reward, reward, now))

    def reputation_summary(self) -> list:
        with self._conn() as c:
            rows = c.execute(
                "SELECT model_id, domain, skill, total_runs, avg_reward "
                "FROM model_reputation ORDER BY domain, skill, avg_reward DESC"
            ).fetchall()
        return [{"model": r[0], "domain": r[1], "skill": r[2],
                 "runs": r[3], "avg_reward": round(r[4], 3)} for r in rows]

    # ── core memory ───────────────────────────────────────────────────

    def read(self, namespace: str, key: str):
        with self._conn() as c:
            r = c.execute(
                "SELECT value FROM memory WHERE namespace=? AND key=?",
                (namespace, key),
            ).fetchone()
        return json.loads(r[0]) if r else None

    def write(self, owner: str, key: str, value, caller_id: str = None) -> bool:
        if caller_id and caller_id != owner:
            _log("MEM", owner, "WRITE_REJECTED", f"'{caller_id}' tried to write to '{owner}'", "R")
            return False
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO memory VALUES (?,?,?,?)",
                (owner, key, json.dumps(value), datetime.now().isoformat()),
            )
        return True

    def set_system(self, key: str, value) -> None:
        self.write("system", key, value)

    def get_system(self, key: str):
        return self.read("system", key)

    def all_outputs(self, run_id: str = None) -> dict:
        with self._conn() as c:
            if run_id:
                rows = c.execute(
                    """SELECT m.namespace, m.value FROM memory m
                       INNER JOIN agents a ON m.namespace = a.agent_id
                       WHERE m.key = 'result' AND a.run_id = ?""",
                    (run_id,),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT namespace, value FROM memory WHERE key='result'"
                ).fetchall()
        return {ns: json.loads(v) for ns, v in rows}

    # ── messaging ─────────────────────────────────────────────────────

    def send(self, from_a: str, to_a: str, mtype: str, subject: str, body) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO messages "
                "(from_agent, to_agent, msg_type, subject, body, sent_at) "
                "VALUES (?,?,?,?,?,?)",
                (from_a, to_a, mtype, subject, json.dumps(body), datetime.now().isoformat()),
            )

    def all_messages(self, run_id: str = None, after_ts: str = None) -> list:
        with self._conn() as c:
            if after_ts:
                rows = c.execute(
                    "SELECT from_agent, to_agent, msg_type, subject, sent_at "
                    "FROM messages WHERE sent_at >= ? ORDER BY sent_at",
                    (after_ts,),
                ).fetchall()
            else:
                rows = c.execute(
                    "SELECT from_agent, to_agent, msg_type, subject, sent_at "
                    "FROM messages ORDER BY sent_at"
                ).fetchall()
        return rows

    # ── agent lifecycle ───────────────────────────────────────────────

    def register(self, agent_id: str, role: str, by: str, depth: int,
                 model_id: str = None, skill: str = None,
                 domain: str = None, run_id: str = None) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO agents "
                "(agent_id, role, status, depth, spawned_by, started_at, "
                "model_id, skill, domain, run_id) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (agent_id, role, "running", depth, by,
                 datetime.now().isoformat(), model_id, skill, domain, run_id),
            )

    def finish(self, agent_id: str, success: bool = True,
               quality: float = 0.0, drift: float = 0.0, tokens: int = 0) -> None:
        with self._conn() as c:
            c.execute(
                "UPDATE agents SET status=?, ended_at=?, success=?, "
                "quality=?, drift=?, tokens=? WHERE agent_id=?",
                ("done" if success else "failed", datetime.now().isoformat(),
                 1 if success else 0, quality, drift, tokens, agent_id),
            )

    def completed_agents(self) -> list:
        with self._conn() as c:
            rows = c.execute("SELECT agent_id FROM agents WHERE success=1").fetchall()
        return [r[0] for r in rows]

    def agent_info(self, agent_id: str) -> dict:
        with self._conn() as c:
            row = c.execute(
                "SELECT role, depth, quality, drift, tokens, model_id, skill, domain "
                "FROM agents WHERE agent_id=?",
                (agent_id,),
            ).fetchone()
        if not row:
            return {}
        return {"role": row[0], "depth": row[1], "quality": row[2],
                "drift": row[3], "tokens": row[4],
                "model_id": row[5], "skill": row[6], "domain": row[7]}

    def stats(self, run_id: str = None, started_at: str = None) -> dict:
        with self._conn() as c:
            if run_id:
                t  = c.execute("SELECT COUNT(*) FROM agents WHERE run_id=?", (run_id,)).fetchone()[0]
                ok = c.execute("SELECT COUNT(*) FROM agents WHERE run_id=? AND success=1", (run_id,)).fetchone()[0]
                fl = c.execute("SELECT COUNT(*) FROM agents WHERE run_id=? AND status='failed'", (run_id,)).fetchone()[0]
                aq = c.execute("SELECT AVG(quality) FROM agents WHERE run_id=? AND success=1", (run_id,)).fetchone()[0] or 0
                ad = c.execute("SELECT AVG(drift)   FROM agents WHERE run_id=? AND success=1", (run_id,)).fetchone()[0] or 0
            else:
                t  = c.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
                ok = c.execute("SELECT COUNT(*) FROM agents WHERE success=1").fetchone()[0]
                fl = c.execute("SELECT COUNT(*) FROM agents WHERE status='failed'").fetchone()[0]
                aq = c.execute("SELECT AVG(quality) FROM agents WHERE success=1").fetchone()[0] or 0
                ad = c.execute("SELECT AVG(drift)   FROM agents WHERE success=1").fetchone()[0] or 0

            if started_at:
                ms = c.execute("SELECT COUNT(*) FROM messages WHERE sent_at >= ?", (started_at,)).fetchone()[0]
                sp = c.execute("SELECT COUNT(*) FROM spawns WHERE requested_at >= ?", (started_at,)).fetchone()[0]
                rj = c.execute("SELECT COUNT(*) FROM spawns WHERE status='rejected' AND requested_at >= ?", (started_at,)).fetchone()[0]
                fo = c.execute("SELECT COUNT(*) FROM fossils WHERE died_at >= ?", (started_at,)).fetchone()[0]
                gb = c.execute("SELECT COUNT(*) FROM guardrail_log WHERE verdict='blocked' AND ts >= ?", (started_at,)).fetchone()[0]
            else:
                ms = c.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
                sp = c.execute("SELECT COUNT(*) FROM spawns").fetchone()[0]
                rj = c.execute("SELECT COUNT(*) FROM spawns WHERE status='rejected'").fetchone()[0]
                fo = c.execute("SELECT COUNT(*) FROM fossils").fetchone()[0]
                gb = c.execute("SELECT COUNT(*) FROM guardrail_log WHERE verdict='blocked'").fetchone()[0]

        return {"agents": t, "success": ok, "failed": fl,
                "messages": ms, "spawns": sp, "spawn_rejected": rj,
                "fossils": fo, "guardrail_blocked": gb,
                "avg_quality": round(aq, 3), "avg_drift": round(ad, 3)}

    # ── sub-spawning ──────────────────────────────────────────────────

    def request_spawn(self, by: str, depth: int, name: str,
                      role: str, task: str, tools: list, score: float) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO spawns "
                "(requested_by, depth, name, role, task, tools, score, requested_at) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (by, depth, name, role, task, json.dumps(tools), score, datetime.now().isoformat()),
            )

    def pending_spawns(self) -> list:
        with self._conn() as c:
            rows = c.execute(
                "SELECT id, requested_by, depth, name, role, task, tools, score "
                "FROM spawns WHERE status='pending' ORDER BY score DESC"
            ).fetchall()
        return [{"id": r[0], "by": r[1], "depth": r[2], "name": r[3],
                 "role": r[4], "task": r[5], "tools": json.loads(r[6]),
                 "score": r[7]} for r in rows]

    def close_spawn(self, sid: int, status: str = "done") -> None:
        with self._conn() as c:
            c.execute("UPDATE spawns SET status=? WHERE id=?", (status, sid))

    # ── fossil record ─────────────────────────────────────────────────

    def deposit_fossil(self, agent_id: str, role: str, task_summary: str,
                       constitution: str, quality: float, drift: float,
                       tokens: int, runtime: float, depth: int) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO fossils "
                "(agent_id, role, task_summary, constitution, "
                "quality, drift, tokens, runtime, depth, died_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?)",
                (agent_id, role, task_summary[:500], constitution[:2000],
                 quality, drift, tokens, runtime, depth, datetime.now().isoformat()),
            )
        _log("FOSSIL", agent_id, "DEPOSITED", f"q={quality:.2f} d={drift:.2f} depth={depth}", "W")

    # ── souls (persistent agent identity) ────────────────────────────

    def get_soul(self, role: str, min_runs: int = 3) -> dict | None:
        role = role.strip().lower()[:50] if role else None
        if not role:
            return None
        with self._conn() as conn:
            conn.row_factory = lambda cursor, row: {
                col[0]: row[idx] for idx, col in enumerate(cursor.description)
            }
            return conn.execute(
                """SELECT soul_id, role, avg_quality, best_quality,
                          total_runs, best_constitution
                   FROM souls
                   WHERE role = ? AND total_runs >= ? AND avg_quality > 0.0
                   LIMIT 1""",
                (role, min_runs),
            ).fetchone()

    def update_soul(self, role: str, quality: float, constitution: str) -> None:
        role = role.strip().lower()[:50] if role else None
        if not role:
            return
        quality = max(0.0, min(1.0, quality))
        soul_id = hashlib.md5(role.encode()).hexdigest()
        now     = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO souls (
                    soul_id, role, avg_quality, best_quality,
                    total_runs, best_constitution, created_at, last_updated)
                VALUES (?, ?, ?, ?, 1, ?, ?, ?)
                ON CONFLICT(soul_id) DO UPDATE SET
                    avg_quality = (souls.avg_quality * souls.total_runs + excluded.avg_quality)
                                  / (souls.total_runs + 1),
                    best_quality = CASE
                        WHEN excluded.best_quality > souls.best_quality
                        THEN excluded.best_quality ELSE souls.best_quality END,
                    best_constitution = CASE
                        WHEN excluded.best_quality > souls.best_quality
                        THEN excluded.best_constitution ELSE souls.best_constitution END,
                    total_runs   = souls.total_runs + 1,
                    last_updated = excluded.last_updated
            """, (soul_id, role, quality, quality, constitution, now, now))
        _log("SOUL", role, "UPDATED", f"q={quality:.2f} soul_id={soul_id[:8]}", "P")

    def increment_soul_attempts(self, role: str) -> None:
        role = role.strip().lower()[:50] if role else None
        if not role:
            return
        soul_id = hashlib.md5(role.encode()).hexdigest()
        now     = datetime.utcnow().isoformat()
        with self._conn() as conn:
            conn.execute("""
                INSERT INTO souls (
                    soul_id, role, avg_quality, best_quality,
                    total_runs, best_constitution, created_at, last_updated)
                VALUES (?, ?, 0.0, 0.0, 1, NULL, ?, ?)
                ON CONFLICT(soul_id) DO UPDATE SET
                    total_runs   = souls.total_runs + 1,
                    last_updated = excluded.last_updated
            """, (soul_id, role, now, now))
        _log("SOUL", role, "ATTEMPT_COUNTED", "failed run recorded", "Y")

    # ── intent / progress / relationships ────────────────────────────

    def log_intent(self, run_id: str, agent_id: str, role: str,
                   drift: float, quality: float,
                   contribution: str = "", wave: str = "gathering") -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO intent_log "
                "(run_id, agent_id, role, drift, quality, contribution, wave, ts) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (run_id, agent_id, role[:80], round(drift, 3), round(quality, 3),
                 contribution[:200], wave, datetime.now().isoformat()),
            )

    def intent_summary(self, run_id: str) -> list:
        with self._conn() as c:
            rows = c.execute(
                "SELECT agent_id, role, drift, quality, contribution, wave "
                "FROM intent_log WHERE run_id=? ORDER BY ts",
                (run_id,),
            ).fetchall()
        return [{"agent_id": r[0], "role": r[1], "drift": r[2],
                 "quality": r[3], "contribution": r[4], "wave": r[5]}
                for r in rows]

    def write_progress(self, agent_id: str, pct: int, msg: str, show: bool = True) -> None:
        with self._conn() as c:
            c.execute("INSERT INTO progress VALUES (?,?,?,?)",
                      (agent_id, int(pct), str(msg), datetime.now().isoformat()))
        if show and self.cfg.get("show_progress"):
            bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
            print(f"\033[96m  [{bar}] {pct:3d}%  {agent_id}: {msg}\033[0m")

    def record_relationship(self, a: str, b: str, run_id: str,
                             sa: float, sb: float) -> None:
        if a > b:
            a, b = b, a
        with self._conn() as c:
            c.execute(
                "INSERT OR REPLACE INTO relationships VALUES (?,?,?,?,?,?)",
                (a, b, run_id, sa, sb, datetime.now().isoformat()),
            )

    def strong_relationships(self, min_score: float = 0.7) -> list:
        with self._conn() as c:
            rows = c.execute(
                "SELECT agent_a, agent_b, "
                "AVG(score_a+score_b)/2 as avg, COUNT(*) as runs "
                "FROM relationships GROUP BY agent_a, agent_b "
                "HAVING avg>? ORDER BY avg DESC",
                (min_score,),
            ).fetchall()
        return [{"a": r[0], "b": r[1], "avg": round(r[2], 3), "runs": r[3]} for r in rows]

    def log_guardrail(self, agent_id: str, layer: str, verdict: str, detail: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO guardrail_log (agent_id, layer, verdict, detail, ts) "
                "VALUES (?,?,?,?,?)",
                (agent_id, layer, verdict, detail[:300], datetime.now().isoformat()),
            )
