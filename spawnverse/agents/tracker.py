# spawnverse/agents/tracker.py
from ..memory.db import DistributedMemory


class IntentTracker:
    """
    Tracks every agent's drift + quality score for the current run and
    prints a formatted alignment report at the end.
    """

    WEAK_THRESHOLD = 0.45
    WARN_THRESHOLD = 0.65

    def __init__(self, run_id: str, task_desc: str, mem: DistributedMemory) -> None:
        self.run_id    = run_id
        self.task_desc = task_desc
        self.mem       = mem
        self._entries: list = []

    def track(self, agent_id: str, role: str, drift: float,
              quality: float, output, wave: str = "gathering") -> None:
        contribution = self._summarise(agent_id, output)
        self._entries.append({
            "agent_id": agent_id, "role": role,
            "drift":    round(drift,   3),
            "quality":  round(quality, 3),
            "contribution": contribution,
            "wave":     wave,
        })
        self.mem.log_intent(self.run_id, agent_id, role, drift, quality, contribution, wave)

    def print_report(self) -> None:
        if not self._entries:
            return

        drifts    = [e["drift"]   for e in self._entries]
        qualities = [e["quality"] for e in self._entries]
        sys_drift = round(sum(drifts)    / len(drifts),    3)
        sys_qual  = round(sum(qualities) / len(qualities),  3)

        weak    = [e for e in self._entries if e["drift"] < self.WEAK_THRESHOLD]
        gathering = [e for e in self._entries if e["wave"] == "gathering"]
        synthesis = [e for e in self._entries if e["wave"] == "synthesis"]
        g_avg   = round(sum(e["drift"] for e in gathering) / len(gathering), 3) if gathering else None
        s_avg   = round(sum(e["drift"] for e in synthesis) / len(synthesis), 3) if synthesis else None

        div  = "═" * 66
        sdiv = "─" * 66
        print(f"\n{div}\n  INTENT ALIGNMENT REPORT\n  Task: {self.task_desc[:60]}\n{sdiv}")
        print(f"  System Alignment : {sys_drift:.2f}  {self._bar(sys_drift)}  quality={sys_qual:.2f}\n")
        print(f"  AGENT CONTRIBUTIONS  ({len(self._entries)} agents):")

        for e in self._entries:
            d    = e["drift"]
            flag = "  ✅" if d >= self.WARN_THRESHOLD else ("  ⚠️" if d >= self.WEAK_THRESHOLD else "  🔴 WEAK")
            aid  = e["agent_id"][:30]
            print(f"    {aid:<30}  drift={d:.2f}  {self._bar(d)}{flag}")
            print(f"    {'':30}  {e['contribution'][:60]}")

        if weak:
            print(f"\n  🔴 WEAK LINKS:")
            for e in weak:
                print(f"    {e['agent_id']}  drift={e['drift']:.2f}")

        if g_avg is not None or s_avg is not None:
            print(f"\n  CHAIN ANALYSIS:")
            if g_avg is not None:
                print(f"    Gathering wave avg drift : {g_avg:.2f}  {self._bar(g_avg)}")
            if s_avg is not None:
                delta = round(s_avg - g_avg, 3) if g_avg is not None else 0
                sign  = "+" if delta >= 0 else ""
                print(f"    Synthesis wave avg drift : {s_avg:.2f}  {self._bar(s_avg)}  ({sign}{delta} vs gathering)")

        print(f"{div}\n")

    # ── private ───────────────────────────────────────────────────────

    def _summarise(self, agent_id: str, output) -> str:
        if not output:
            return "no output"
        if isinstance(output, list):
            first = output[0] if output else {}
            keys  = [str(k) for k in first.keys() if str(k) != "raw"][:3] if isinstance(first, dict) else []
            return (f"{agent_id}: list[{len(output)}] [{', '.join(keys)}]" if keys
                    else f"{agent_id}: list[{len(output)}]")
        if not isinstance(output, dict):
            return "no output"
        keys = [str(k) for k in output.keys() if str(k) != "raw"][:4]
        return f"{agent_id}: [{', '.join(keys)}]" if keys else "empty result"

    @staticmethod
    def _bar(score: float, width: int = 10) -> str:
        filled = round(score * width)
        return "█" * filled + "░" * (width - filled)
