# spawnverse/orchestrator.py
import os
import time
import textwrap
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

from .config import DEFAULT_CONFIG, MODEL_REGISTRY
from .display import _log
from .llm import _make_client, _llm, _safe_json, reset_budget, get_tokens_used
from .memory.db import DistributedMemory
from .vectordb.store import VectorDB
from .guardrails.checks import Guardrails
from .scoring.drift import IntentDriftScorer
from .scoring.quality import OutputQualityScorer
from .scoring.spawn import SpawnScorer
from .routing.complexity import ComplexityScorer
from .routing.router import ModelRouter
from .routing.reward import RewardEngine
from .agents.generator import Generator
from .agents.executor import Executor
from .agents.tracker import IntentTracker
from .apis.registry import detect_needed_apis, build_api_stdlib


class Orchestrator:
    """
    Top-level runtime.

    Lifecycle per run:
      1. Decompose task → LLM returns a list of agent specs (DAG)
      2. DAG scheduling  → run ready agents in parallel waves
      3. Per-agent       → route model → generate code → execute → score → reward
      4. Summary         → intent report + routing audit + stats
    """

    def __init__(self, config: dict = None) -> None:
        self.cfg = {**DEFAULT_CONFIG, **(config or {})}

        if not os.environ.get("GROQ_API_KEY"):
            raise EnvironmentError(
                "GROQ_API_KEY is not set.\n"
                "    export GROQ_API_KEY=your_key_here\n"
                "    https://console.groq.com/keys"
            )

        self.client  = _make_client(self.cfg)
        self.mem     = DistributedMemory(self.cfg)
        self.vdb     = VectorDB(self.cfg)
        self.guard   = Guardrails()
        self.gen     = Generator()
        self.exe     = Executor()
        self.drift   = IntentDriftScorer()
        self.quality = OutputQualityScorer()
        self.spawner = SpawnScorer()
        self.t0           = time.time()
        self.run_id       = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._started_at  = datetime.now().isoformat()
        self.consts: dict             = {}
        self.intent: IntentTracker | None = None

        self.complexity_scorer = ComplexityScorer()
        self.model_router      = ModelRouter(self.cfg)
        self.reward_engine     = RewardEngine()
        self._routing_audit: list = []

        self._api_names  = []
        self._api_stdlib = ""

        routing_status = (
            f"ON (explore_c={self.cfg['routing_explore_c']} "
            f"drift_threshold={self.cfg['drift_threshold']})"
            if self.cfg["model_routing"] else "OFF"
        )
        _log("ORCH", "SYSTEM", "BOOT",
             f"run_id={self.run_id} routing={routing_status} "
             f"vdb={self.cfg['vector_db_enabled']} depth={self.cfg['max_depth']}", "M")

    # ── public entry point ────────────────────────────────────────────

    def run(self, task: dict, knowledge_base: list = None) -> dict:
        reset_budget()
        self._routing_audit = []

        desc = task["description"]
        ctx  = task.get("context", {})
        fmt  = self.cfg["output_format"]

        self._print_header(desc)

        self.mem.set_system("project", {
            "description": desc, "context": ctx,
            "output_format": fmt, "run_id": self.run_id,
            "started_at": datetime.now().isoformat(),
        })

        self._setup_apis(desc)

        if self.cfg["vector_db_enabled"] and knowledge_base:
            self._index_knowledge(knowledge_base)

        print(f"\n{'─'*66}\n  PHASE 1 — DECOMPOSE TASK\n{'─'*66}\n")
        agents = self._decompose(desc, fmt)

        self.intent = IntentTracker(self.run_id, desc, self.mem)

        print(f"\n{'─'*66}\n  PHASE 2 — DAG SCHEDULING\n{'─'*66}\n")
        self._run_dag(agents)

        self._print_messages()

        outputs = self.mem.all_outputs(run_id=self.run_id)
        self._print_outputs(desc, outputs)
        self._print_summary(self.run_id, self._started_at)

        if self.intent is not None:
            self.intent.print_report()

        self._print_routing_audit()

        return outputs

    # ── decomposition ─────────────────────────────────────────────────

    def _decompose(self, task_desc: str, fmt: str) -> list:
        _log("ORCH", "LLM", "DECOMPOSE", task_desc[:100], "P")
        n1, n2 = self.cfg["wave1_agents"], self.cfg["wave2_agents"]

        text, _ = _llm(self.client, self.cfg, [
            {"role": "system", "content": "Return ONLY a valid JSON array. No markdown. Start with [."},
            {"role": "user",   "content": (
                f"Plan specialist agents for:\nTASK: {task_desc}\nFMT: {fmt}\n\n"
                f"Create {n1} gathering agents (depends_on=[]) and {n2} synthesis agents.\n"
                "Each object: agent_id(snake_case), role(20+chars), "
                "task(30+chars), tools_needed(list), depends_on(list).\n"
                "Return ONLY the JSON array."
            )},
        ], max_tokens=2000)

        agents = _safe_json(text)
        if not isinstance(agents, list):
            agents = []

        self.mem.set_system("plan", agents)
        self.mem.set_system("task_desc", task_desc)
        _log("ORCH", "ALL", "PLAN",
             "\n".join(
                 f"  [{i+1}] {a.get('agent_id','?'):28s} "
                 f"deps={a.get('depends_on',[])} | {a.get('role','')[:50]}"
                 for i, a in enumerate(agents)
             ), "Y")
        return agents

    # ── DAG execution ─────────────────────────────────────────────────

    def _run_dag(self, agents: list) -> None:
        pending   = list(agents)
        completed: set = set()
        iteration = 1

        while pending:
            ready = [a for a in pending
                     if set(a.get("depends_on", [])).issubset(completed)]

            if not ready:
                self._log_dag_deadlock(pending, completed)
                raise RuntimeError(f"DAG deadlock: {len(pending)} agents blocked")

            ready_ids = {a["agent_id"] for a in ready}
            waiting   = [a["agent_id"] for a in pending if a["agent_id"] not in ready_ids]
            _log("ORCH", "DAG", "STATE",
                 f"iteration={iteration} completed={sorted(completed)} "
                 f"waiting={waiting} ready={sorted(ready_ids)}", "B")

            self._run_wave(ready, depth=0,
                           label=f"DAG iteration={iteration} — {len(ready)} agent(s)")
            completed.update(ready_ids)
            pending = [a for a in pending if a["agent_id"] not in completed]
            self._handle_spawns(pending, completed)
            iteration += 1

    def _run_wave(self, specs: list, depth: int = 0, label: str = "") -> None:
        if not specs:
            return
        print(f"\n{'─'*66}\n  {label} — {len(specs)} agent(s)\n{'─'*66}\n")
        if self.cfg["parallel"] and len(specs) > 1:
            with ThreadPoolExecutor(
                    max_workers=min(len(specs), self.cfg["max_parallel"])) as pool:
                futures = {pool.submit(self._spawn, s, "orchestrator", depth): s["agent_id"]
                           for s in specs}
                for fut in as_completed(futures):
                    try:
                        fut.result()
                    except Exception as e:
                        _log("ORCH", futures[fut], "ERR", str(e), "R")
        else:
            for s in specs:
                self._spawn(s, depth=depth)

    def _handle_spawns(self, pending: list, completed: set) -> None:
        spawn_requests = self.mem.pending_spawns()
        if not spawn_requests:
            return
        _log("ORCH", "SPAWNS", "CHECK", f"{len(spawn_requests)} pending", "M")
        existing_ids = {a["agent_id"] for a in pending} | completed

        for req in spawn_requests:
            score  = self.spawner.score(req["name"], req["role"], req["task"], existing_ids)
            reject = None
            if req["depth"] > self.cfg["max_depth"]:
                reject = f"depth {req['depth']} > max"
            elif score < self.cfg["min_spawn_score"]:
                reject = f"score {score} too low"
            elif len(req["role"]) < 15:
                reject = "role too short"
            elif len(req["task"]) < 20:
                reject = "task too short"
            elif req["name"] in existing_ids:
                reject = "duplicate"

            if reject:
                _log("ORCH", req["name"], "SPAWN_REJECTED", reject, "Y")
                self.mem.close_spawn(req["id"], "rejected")
                continue

            new_spec = {"agent_id": req["name"], "role": req["role"],
                        "task": req["task"], "tools_needed": req["tools"], "depends_on": []}
            pending.append(new_spec)
            existing_ids.add(req["name"])
            self.mem.close_spawn(req["id"])
            _log("ORCH", req["name"], "SPAWN_QUEUED", "added to DAG pending pool", "Y")

    # ── single agent lifecycle ────────────────────────────────────────

    def _spawn(self, spec: dict, spawned_by: str = "orchestrator",
               depth: int = 0, retry: bool = False) -> bool:
        aid      = spec["agent_id"]
        task_desc= self.mem.get_system("task_desc") or ""
        ctx      = self.mem.get_system("project") or {}

        model_id, complexity, skill, domain = self._route_model(spec)

        self.mem.register(aid, spec["role"], spawned_by, depth,
                          model_id=model_id, skill=skill, domain=domain,
                          run_id=self.run_id)

        is_synthesis = bool(spec.get("depends_on"))

        dep_ids = spec.get("depends_on") or []

        code, gen_tokens = self.gen.generate(
            self.client, self.cfg,
            aid, spec["role"], spec["task"],
            spec.get("tools_needed", ["llm_reasoning"]),
            ctx, depth, self.cfg["output_format"],
            vdb_enabled=self.cfg["vector_db_enabled"],
            retry=retry,
            api_stdlib=self._api_stdlib,
            mem=self.mem,
            guard=self.guard,
            model_id=model_id,
            is_synthesis=is_synthesis,
            depends_on=dep_ids,
        )
        self.consts[aid] = code

        ok, elapsed = self.exe.run(aid, code, self.cfg, depth, self.guard, self.mem)

        if not ok and self.cfg["retry_failed"] and not retry:
            _log("ORCH", aid, "RETRY", "Retrying with simpler prompt", "Y")
            code2, _ = self.gen.generate(
                self.client, self.cfg,
                aid, spec["role"], spec["task"],
                spec.get("tools_needed", ["llm_reasoning"]),
                ctx, depth, self.cfg["output_format"],
                vdb_enabled=self.cfg["vector_db_enabled"],
                retry=True,
                api_stdlib=self._api_stdlib,
                model_id=model_id,
                is_synthesis=is_synthesis,
                depends_on=dep_ids,
            )
            self.consts[aid] = code2
            ok, elapsed = self.exe.run(aid, code2, self.cfg, depth, self.guard, self.mem)

        quality_score, drift_score = 0.0, 0.5

        if ok:
            output = self.mem.read(aid, "result") or {}
            ok     = self._apply_output_guardrails(aid, spec["task"], output)

        if ok:
            output        = self.mem.read(aid, "result") or {}
            quality_score = self.quality.score(spec["task"], output, self.client, self.cfg)
            drift_score   = self.drift.score(task_desc, spec["role"], output, self.client, self.cfg)

            if self.cfg["vector_db_enabled"]:
                self.vdb.index_output(aid, spec["role"], output, spec["task"][:100])

            _log("ORCH", aid, "SCORES", f"quality={quality_score:.2f} drift={drift_score:.2f}", "C")

            if self.intent is not None:
                wave = "synthesis" if spec.get("depends_on") else "gathering"
                self.intent.track(aid, spec["role"], drift_score, quality_score, output, wave)

        reward = self._apply_reward(aid, model_id, drift_score, quality_score, skill, domain, ok)

        self._routing_audit.append({
            "agent_id": aid, "model": model_id, "skill": skill, "domain": domain,
            "quality": quality_score, "drift": drift_score, "reward": reward, "ok": ok,
        })

        for other in self.mem.completed_agents():
            if other != aid:
                info = self.mem.agent_info(other)
                self.mem.record_relationship(aid, other, self.run_id,
                                             quality_score, info.get("quality", 0.0))

        self.mem.finish(aid, ok, quality_score, drift_score, gen_tokens)

        constitution = (self.consts.get(aid) or "")[:2000]
        self.mem.deposit_fossil(aid, spec["role"], spec["task"][:500],
                                constitution, quality_score, drift_score,
                                gen_tokens, elapsed, depth)

        if ok and quality_score > 0.05:
            self.mem.update_soul(spec["role"], quality_score, constitution)
        elif not ok:
            self.mem.increment_soul_attempts(spec["role"])

        _log("ORCH", aid, "LIFECYCLE",
             f"{'OK' if ok else 'FAILED'} q={quality_score:.2f} d={drift_score:.2f} "
             f"model={model_id} reward={reward:+.3f}",
             "G" if ok else "R")
        return ok

    # ── model routing ─────────────────────────────────────────────────

    def _route_model(self, spec: dict) -> tuple:
        if not self.cfg["model_routing"]:
            return self.cfg["model"], 0.5, "general", "general"

        complexity, skill, domain = self.complexity_scorer.score(spec)
        model_id  = self.model_router.assign(spec, complexity, skill, domain, self.mem)
        model_info = MODEL_REGISTRY.get(model_id, {})

        _log("ROUTE", spec["agent_id"], "ASSIGNED",
             f"model={model_id} (tier {model_info.get('tier','?')}) "
             f"skill={skill} domain={domain} complexity={complexity}", "C")
        return model_id, complexity, skill, domain

    def _apply_reward(self, agent_id: str, model_id: str, drift: float,
                      quality: float, skill: str, domain: str, ok: bool) -> float:
        if not self.cfg["model_routing"]:
            return 0.0

        reward = self.reward_engine.compute(
            model_id,
            drift   if ok else 0.0,
            quality if ok else 0.0,
            domain, skill, self.cfg,
        )
        self.mem.update_model_reputation(model_id, domain, skill, reward)

        flag = "✅" if reward > 0 else "🔴"
        _log("REWARD", agent_id, "RECORDED",
             f"model={model_id} skill={skill} reward={reward:+.3f} {flag}", "C")
        return reward

    # ── guardrail application ─────────────────────────────────────────

    def _apply_output_guardrails(self, agent_id: str, task: str, output) -> bool:
        if self.cfg["guardrail_output"]:
            valid, reason = self.guard.validate_output(agent_id, output)
            if not valid:
                self.mem.log_guardrail(agent_id, "output", "blocked", reason)
                _log("GUARD", agent_id, "OUTPUT_BLOCKED", reason, "R")
                return False

        if self.cfg["guardrail_semantic"]:
            safe, reason = self.guard.semantic_check(
                agent_id, task, output, self.client, self.cfg)
            if not safe:
                self.mem.log_guardrail(agent_id, "semantic", "blocked", reason)
                return False

        return True

    # ── setup helpers ─────────────────────────────────────────────────

    def _setup_apis(self, desc: str) -> None:
        if self.cfg.get("external_apis", False) is False:
            return
        self._api_names  = detect_needed_apis(desc, self.cfg, self.client)
        if self._api_names:
            self._api_stdlib = build_api_stdlib(
                self._api_names, self.cfg.get("external_api_key", {}))
            _log("API", "AUTO", "INJECTING HELPERS", str(self._api_names), "C")

    def _index_knowledge(self, knowledge_base: list) -> None:
        print(f"\n{'─'*66}\n  PHASE 0 — INDEXING KNOWLEDGE BASE\n{'─'*66}\n")
        for doc in knowledge_base:
            self.vdb.ingest(doc)

    # ── display helpers ───────────────────────────────────────────────

    def _print_header(self, desc: str) -> None:
        print(f"\n{'═'*66}")
        print(f"  SPAWNVERSE  —  Self-Spawning Cognitive Agent System")
        print(f"  run_id = {self.run_id}")
        print(f"  {desc[:62]}")
        print(f"{'═'*66}\n")

    def _print_messages(self) -> None:
        if not self.cfg["show_messages"]:
            return
        print(f"\n{'═'*66}\n  AGENT COMMUNICATION LOG\n{'═'*66}\n")
        for fa, ta, mt, subj, ts in self.mem.all_messages(after_ts=self._started_at):
            print(f"  [{ts}]  {fa:22s} ──→  {ta}")
            print(f"  {mt:15s} | {subj}\n")

    def _print_outputs(self, desc: str, outputs: dict) -> None:
        print(f"\n{'═'*66}\n  FINAL OUTPUTS\n  {desc[:60]}\n{'═'*66}\n")
        for agent_id, result in outputs.items():
            info = self.mem.agent_info(agent_id)
            q, d = info.get("quality", 0), info.get("drift", 0)
            flag = " ⚠️" if (q < self.cfg["quality_min"] or d < self.cfg["drift_warn"]) else ""
            mid  = info.get("model_id", "—")
            skl  = info.get("skill",    "—")
            print(f"{'─'*66}")
            print(f"  {agent_id.upper().replace('_', ' ')}{flag}")
            print(f"  quality={q:.2f}  drift={d:.2f}  model={mid}  skill={skl}")
            print(f"{'─'*66}")
            _show(result)
            print()

    def _print_summary(self, run_id: str = None, started_at: str = None) -> None:
        stats   = self.mem.stats(run_id=run_id, started_at=started_at)
        elapsed = round(time.time() - self.t0, 1)
        rels    = self.mem.strong_relationships()

        print(f"{'═'*66}\n  EXECUTION SUMMARY\n{'─'*66}")
        print(f"  Agents         : {stats['agents']} ({stats['success']} ok, {stats['failed']} failed)")
        print(f"  Quality / Drift: {stats['avg_quality']:.2f} / {stats['avg_drift']:.2f}")
        print(f"  Messages       : {stats['messages']}")
        print(f"  Spawns         : {stats['spawns']} ({stats['spawn_rejected']} rejected)")
        print(f"  Fossils        : {stats['fossils']}")
        print(f"  Guard blocks   : {stats['guardrail_blocked']}")
        print(f"  Tokens used    : {get_tokens_used():,}/{self.cfg['token_budget']:,}")
        print(f"  Wall time      : {elapsed}s")
        if rels:
            print(f"{'─'*66}\n  AGENT RELATIONSHIPS")
            for r in rels[:3]:
                print(f"    {r['a']} ↔ {r['b']}  avg={r['avg']}  runs={r['runs']}")
        print(f"{'═'*66}\n")

    def _print_routing_audit(self) -> None:
        if not self._routing_audit or not self.cfg["model_routing"]:
            return
        div  = "═" * 66
        sdiv = "─" * 66
        print(f"\n{div}\n  MODEL ROUTING AUDIT\n{sdiv}")
        print(f"  {'AGENT':<28} {'MODEL':<14} {'SKILL':<12} {'Q':>5} {'D':>5} {'REWARD':>8}")
        print(f"  {sdiv}")
        for e in self._routing_audit:
            flag = "✅" if e["reward"] > 0 else "🔴"
            print(f"  {e['agent_id'][:27]:<28} "
                  f"{e['model']:<14} "
                  f"{e['skill']:<12} "
                  f"{e['quality']:>5.2f} "
                  f"{e['drift']:>5.2f} "
                  f"{e['reward']:>+8.3f}  {flag}")
        total = sum(e["reward"] for e in self._routing_audit)
        print(f"  {sdiv}")
        print(f"  {'Total reward':>60}: {total:+.3f}")

        rep = self.mem.reputation_summary()
        if rep:
            print(f"\n  ACCUMULATED REPUTATION  (all runs)\n  {sdiv}")
            print(f"  {'MODEL':<14} {'DOMAIN':<12} {'SKILL':<12} {'RUNS':>5} {'AVG_REWARD':>10}")
            print(f"  {sdiv}")
            for r in rep:
                bar = "█" * int(max(0, r["avg_reward"]) * 5)
                print(f"  {r['model']:<14} {r['domain']:<12} {r['skill']:<12} "
                      f"{r['runs']:>5} {r['avg_reward']:>+10.3f}  {bar}")
        print(f"{div}\n")

    def _log_dag_deadlock(self, pending: list, completed: set) -> None:
        all_ids = {a["agent_id"] for a in pending} | completed
        for a in pending:
            for dep in a.get("depends_on", []):
                if dep not in all_ids:
                    _log("ORCH", "DAG", "MISSING_DEP",
                         f"{a['agent_id']} depends on unknown {dep!r}", "R")
                else:
                    _log("ORCH", "DAG", "UNMET_DEP",
                         f"{a['agent_id']} waiting for {dep!r}", "W")


# ── module-level display helper ───────────────────────────────────────

def _show(v, pad: int = 2) -> None:
    sp = " " * pad
    if isinstance(v, dict):
        for k, vv in v.items():
            if isinstance(vv, (dict, list)):
                print(f"{sp}{k}:")
                _show(vv, pad + 2)
            else:
                val = str(vv)
                if len(val) > 64:
                    print(f"{sp}{k}:")
                    for line in textwrap.wrap(val, 60 - pad):
                        print(f"{sp}  {line}")
                else:
                    print(f"{sp}{k:22s}: {val}")
    elif isinstance(v, list):
        for item in v:
            if isinstance(item, dict):
                _show(item, pad)
                print()
            else:
                print(f"{sp}• {item}")
    else:
        for line in textwrap.wrap(str(v), 60 - pad):
            print(f"{sp}{line}")
