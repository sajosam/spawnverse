"""
debug.py — SpawnVerse Run Inspector
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Shows exactly why agents failed in the last run.

Usage:
    python debug.py                  # reads spawnverse.db
    python debug.py myrun.db         # reads a specific db
    python debug.py --tail           # live tail during a run
"""

import sys, os, json, sqlite3, textwrap
from datetime import datetime

DB = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith("--") else "spawnverse.db"
TAIL = "--tail" in sys.argv

C = {
    "G": "\033[92m", "R": "\033[91m", "Y": "\033[93m",
    "C": "\033[96m", "M": "\033[95m", "D": "\033[90m",
    "W": "\033[37m", "B": "\033[94m",
}
RST  = "\033[0m"
BOLD = "\033[1m"

def c(color, text): return f"{C[color]}{text}{RST}"
def bold(text): return f"{BOLD}{text}{RST}"
def hr(char="─", n=66): print(char * n)

def conn():
    if not os.path.exists(DB):
        print(c("R", f"DB not found: {DB}"))
        print(c("D", "Run a task first, then re-run debug.py"))
        sys.exit(1)
    cx = sqlite3.connect(DB, timeout=10)
    cx.row_factory = sqlite3.Row
    return cx


def show_agents():
    with conn() as cx:
        rows = cx.execute(
            "SELECT agent_id, role, status, depth, quality, drift, "
            "tokens, spawned_by, started_at, ended_at, success "
            "FROM agents ORDER BY started_at"
        ).fetchall()

    if not rows:
        print(c("Y", "No agents found in DB."))
        return

    hr("═")
    print(bold("  AGENT STATUS"))
    hr("═")

    for r in rows:
        icon  = c("G", "✅") if r["success"] else c("R", "❌")
        depth = c("D", f"d={r['depth']}")
        q     = f"q={r['quality']:.2f}" if r['quality'] else "q=n/a"
        d     = f"drift={r['drift']:.2f}" if r['drift'] else "drift=n/a"
        tok   = f"{r['tokens']:,} tok" if r['tokens'] else ""
        t_end = r['ended_at'][:19] if r['ended_at'] else "running..."

        # runtime
        try:
            t0 = datetime.fromisoformat(r['started_at'])
            t1 = datetime.fromisoformat(r['ended_at']) if r['ended_at'] else datetime.now()
            runtime = f"{(t1-t0).total_seconds():.1f}s"
        except Exception:
            runtime = ""

        print(f"  {icon}  {bold(r['agent_id'])}")
        print(f"     {c('D', r['role'][:60])}")
        print(f"     {depth}  {c('C', q)}  {c('C', d)}  {c('D', tok)}  {c('D', runtime)}")
        print(f"     spawned_by={c('D', r['spawned_by'])}  ended={c('D', t_end)}")

        if not r["success"]:
            # Show guardrail blocks for this agent
            with conn() as cx:
                gl = cx.execute(
                    "SELECT layer, verdict, detail FROM guardrail_log WHERE agent_id=?",
                    (r["agent_id"],)
                ).fetchall()
            if gl:
                for g in gl:
                    print(f"     {c('R', '🛡 GUARD')} layer={g['layer']}  verdict={g['verdict']}")
                    print(f"       {c('Y', g['detail'][:100])}")

        print()


def show_guardrail_blocks():
    with conn() as cx:
        rows = cx.execute(
            "SELECT agent_id, layer, verdict, detail, ts "
            "FROM guardrail_log ORDER BY ts"
        ).fetchall()

    if not rows:
        print(c("G", "  No guardrail blocks recorded."))
        return

    hr()
    print(bold("  GUARDRAIL BLOCKS"))
    hr()
    for r in rows:
        verdict_color = "R" if r["verdict"] == "blocked" else "Y"
        print(f"  {c(verdict_color, r['verdict'].upper())}  agent={c('C', r['agent_id'])}  layer={c('M', r['layer'])}")
        print(f"  {c('D', r['detail'][:120])}")
        print()


def show_agent_files():
    """Check .spawnverse_agents/ for generated code and any errors."""
    agents_dir = ".spawnverse_agents"
    if not os.path.exists(agents_dir):
        print(c("D", f"  No agents dir found: {agents_dir}"))
        return

    with conn() as cx:
        failed = cx.execute(
            "SELECT agent_id FROM agents WHERE success=0"
        ).fetchall()
    failed_ids = {r["agent_id"] for r in failed}

    if not failed_ids:
        print(c("G", "  No failed agents to inspect."))
        return

    hr()
    print(bold("  FAILED AGENT CODE SNIPPETS"))
    hr()
    print(c("D", "  (showing last 30 lines of each failed agent file)"))
    print()

    for agent_id in sorted(failed_ids):
        path = os.path.join(agents_dir, f"{agent_id}.py")
        if not os.path.exists(path):
            print(c("Y", f"  {agent_id}.py — file not found (blocked before write)"))
            continue

        lines = open(path, encoding="utf-8", errors="ignore").readlines()
        total = len(lines)
        # Show only the main() function (last 30 lines which are the LLM part)
        snippet = lines[-30:] if total > 30 else lines
        # Find where main() starts
        main_start = next((i for i, l in enumerate(lines) if l.strip().startswith("def main():")), None)
        if main_start is not None:
            snippet = lines[main_start:main_start + 40]

        print(f"  {c('R', '❌')} {bold(agent_id)}.py  ({total} lines total)")
        hr("·")
        for line in snippet:
            print(c("D", "  ") + line.rstrip())
        print()


def show_errors_from_db():
    """Try to extract error info from fossils and memory."""
    with conn() as cx:
        fossils = cx.execute(
            "SELECT agent_id, quality, drift, task_summary "
            "FROM fossils ORDER BY died_at"
        ).fetchall()

    if fossils:
        hr()
        print(bold("  FOSSIL RECORD (all agents that ran)"))
        hr()
        for f in fossils:
            icon = c("G", "✅") if f["quality"] > 0.4 else c("Y", "⚠️ ")
            print(f"  {icon}  {c('C', f['agent_id'])}")
            print(f"     task: {c('D', f['task_summary'][:80])}")
            print(f"     quality={c('C', str(round(f['quality'],2)))}"
                  f"  drift={c('C', str(round(f['drift'],2)))}")
            print()


def show_stats():
    with conn() as cx:
        t  = cx.execute("SELECT COUNT(*) FROM agents").fetchone()[0]
        ok = cx.execute("SELECT COUNT(*) FROM agents WHERE success=1").fetchone()[0]
        fl = cx.execute("SELECT COUNT(*) FROM agents WHERE success=0").fetchone()[0]
        ms = cx.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
        fo = cx.execute("SELECT COUNT(*) FROM fossils").fetchone()[0]
        gb = cx.execute("SELECT COUNT(*) FROM guardrail_log WHERE verdict='blocked'").fetchone()[0]
        aq = cx.execute("SELECT AVG(quality) FROM agents WHERE success=1").fetchone()[0] or 0
        tok= cx.execute("SELECT SUM(tokens) FROM agents").fetchone()[0] or 0

    hr("═")
    print(bold("  RUN SUMMARY"))
    hr("═")
    print(f"  Total agents   : {t}  ({c('G', str(ok))} ok  {c('R', str(fl))} failed)")
    print(f"  Avg quality    : {c('C', f'{aq:.2f}')}")
    print(f"  Messages sent  : {ms}")
    print(f"  Fossils        : {fo}")
    print(f"  Guard blocks   : {c('R' if gb else 'G', str(gb))}")
    print(f"  Total tokens   : {tok:,}")
    hr("═")


def show_fix_hints():
    """Based on what's in the DB, suggest fixes."""
    with conn() as cx:
        failed = cx.execute("SELECT COUNT(*) FROM agents WHERE success=0").fetchone()[0]
        gb     = cx.execute("SELECT COUNT(*) FROM guardrail_log WHERE verdict='blocked'").fetchone()[0]
        layers = cx.execute(
            "SELECT layer, COUNT(*) as n FROM guardrail_log WHERE verdict='blocked' GROUP BY layer"
        ).fetchall()

    if failed == 0:
        return

    hr()
    print(bold("  💡 LIKELY CAUSES + FIXES"))
    hr()

    layer_map = {r["layer"]: r["n"] for r in layers}

    if layer_map.get("code_scan", 0) > 0:
        print(c("Y", f"  ⚠️  Code scan blocked {layer_map['code_scan']} agent(s)"))
        print(c("D", "     LLM generated code with a dangerous pattern (subprocess, os.system, etc.)"))
        print(c("D", "     FIX: These are LLM hallucinations. Retry usually fixes them."))
        print(c("D", "     Set 'retry_failed': True in CONFIG (already default)"))
        print()

    if layer_map.get("output", 0) > 0:
        print(c("Y", f"  ⚠️  Output validation blocked {layer_map['output']} agent(s)"))
        print(c("D", "     Agent wrote an empty result or output was too large/small"))
        print(c("D", "     FIX: Check agent code snippet above. Common cause: agent called"))
        print(c("D", "     done() before write_result(), or LLM returned empty output."))
        print()

    if layer_map.get("semantic", 0) > 0:
        print(c("Y", f"  ⚠️  Semantic guardrail blocked {layer_map['semantic']} agent(s)"))
        print(c("D", "     LLM judge flagged the output as unsafe/off-topic"))
        print(c("D", "     FIX: Try a more specific task description, or temporarily"))
        print(c("D", "     set 'guardrail_semantic': False to debug"))
        print()

    if failed > gb:
        non_guard = failed - gb
        print(c("Y", f"  ⚠️  {non_guard} agent(s) failed without guardrail blocks"))
        print(c("D", "     Most likely: Python runtime error in generated code"))
        print(c("D", "     FIX 1: Check agent file snippets above for syntax errors"))
        print(c("D", "     FIX 2: Add 'retry_failed': True to CONFIG"))
        print(c("D", "     FIX 3: Add 'show_stdout': True to see agent logs"))
        print(c("D", "     FIX 4: Run with 'parallel': False to see errors sequentially"))
        print()

    print(c("C", "  QUICK FIX — add these to your CONFIG:"))
    print()
    print('    CONFIG.update({')
    print('        "retry_failed"       : True,   # retry failed agents')
    print('        "parallel"           : False,  # sequential = easier to debug')
    print('        "guardrail_semantic" : False,  # disable LLM judge temporarily')
    print('        "show_stdout"        : True,   # show all agent output')
    print('    })')
    print()


def tail_mode():
    """Live tail — refresh every 2 seconds during a run."""
    import time
    print(c("C", "Live tail mode — watching for agent updates. Ctrl+C to stop.\n"))
    last_count = 0
    while True:
        try:
            if not os.path.exists(DB):
                print(c("D", f"\r  Waiting for {DB}..."), end="", flush=True)
                time.sleep(2)
                continue
            with conn() as cx:
                rows = cx.execute(
                    "SELECT agent_id, success, quality, drift, status "
                    "FROM agents ORDER BY started_at"
                ).fetchall()
                prog = cx.execute(
                    "SELECT agent_id, pct, message FROM progress "
                    "ORDER BY ts DESC LIMIT 10"
                ).fetchall()

            if len(rows) != last_count:
                os.system("clear" if os.name != "nt" else "cls")
                print(c("C", f"  SpawnVerse Live  ·  {DB}  ·  {datetime.now().strftime('%H:%M:%S')}"))
                hr()
                for r in rows:
                    icon  = c("G", "✅") if r["success"] else (c("Y", "🔄") if r["status"] == "running" else c("R", "❌"))
                    q     = f"q={r['quality']:.2f}" if r['quality'] else ""
                    print(f"  {icon}  {r['agent_id']:30s} {q}")
                hr()
                print(c("D", "  Recent progress:"))
                for p in prog[:5]:
                    bar = "█" * (p["pct"] // 10) + "░" * (10 - p["pct"] // 10)
                    print(f"  [{bar}] {p['pct']:3d}%  {p['agent_id']}: {p['message']}")
                last_count = len(rows)

            time.sleep(2)
        except KeyboardInterrupt:
            print(c("Y", "\n\nStopped."))
            break


# ── Main ──────────────────────────────────────────────────────────

if TAIL:
    tail_mode()
else:
    print(f"\n{bold('SpawnVerse Debug Inspector')}  ·  {c('D', DB)}\n")
    show_stats()
    print()
    show_agents()
    show_guardrail_blocks()
    show_errors_from_db()
    show_agent_files()
    show_fix_hints()