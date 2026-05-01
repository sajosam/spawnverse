# spawnverse/agents/executor.py
import os
import sys
import time
import subprocess

from ..display import _log


class Executor:
    """
    Writes generated agent code to disk and runs it in a subprocess.
    On Linux/macOS applies CPU, RAM, and file-size limits via resource.setrlimit.
    On Windows the sandbox is silently skipped (os.name == 'nt').
    """

    def run(self, agent_id: str, code: str, config: dict,
            depth: int = 0, guardrails=None, mem=None) -> tuple[bool, float]:

        path    = os.path.join(config["agents_dir"], f"{agent_id}.py")
        timeout = config.get(f"timeout_depth{min(depth, 2)}", 60)

        if guardrails and config["guardrail_code"]:
            safe, violations = guardrails.scan_code(agent_id, code, enabled=True)
            if not safe:
                if mem:
                    mem.log_guardrail(agent_id, "code_scan", "blocked", "; ".join(violations))
                _log("GUARD", agent_id, "BLOCKED — not running", f"{len(violations)} violation(s)", "R")
                return False, 0.0

        with open(path, "w", encoding="utf-8") as f:
            f.write(code)

        _log("EXEC", agent_id, f"START d={depth} t={timeout}s", path, "X")
        t0     = time.time()
        kwargs = {
            "capture_output": True,
            "text":           True,
            "timeout":        timeout,
            "env":            os.environ.copy(),
        }
        if os.name != "nt" and config.get("sandbox_enabled"):
            kwargs["preexec_fn"] = self._sandbox(config)

        result  = subprocess.run([sys.executable, path], **kwargs)
        elapsed = round(time.time() - t0, 1)

        if config["show_stdout"]:
            div = "─" * 64
            print(f"\n{div}\n  {agent_id}  ({elapsed}s)\n{div}")
            print(result.stdout if result.stdout.strip() else "  (no output)")
            print(div + "\n")

        if result.returncode != 0:
            stderr_out = result.stderr.strip()
            _log("EXEC", agent_id, f"FAILED rc={result.returncode}",
                 stderr_out[:600] if stderr_out else "(no stderr)", "R")
            return False, elapsed

        _log("EXEC", agent_id, f"DONE {elapsed}s", "", "G")
        return True, elapsed

    @staticmethod
    def _sandbox(config: dict):
        def limit():
            try:
                import resource
                cpu = config["sandbox_cpu_sec"]
                ram = config["sandbox_ram_mb"] * 1024 * 1024
                fsz = config["sandbox_fsize_mb"] * 1024 * 1024
                resource.setrlimit(resource.RLIMIT_CPU,   (cpu, cpu))
                resource.setrlimit(resource.RLIMIT_AS,    (ram, ram))
                resource.setrlimit(resource.RLIMIT_FSIZE, (fsz, fsz))
            except Exception:
                pass
        return limit
