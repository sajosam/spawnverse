# spawnverse/llm.py
import os
import json
import time

from groq import Groq

from .display import _log

_tokens_used: int = 0


def reset_budget() -> None:
    global _tokens_used
    _tokens_used = 0


def get_tokens_used() -> int:
    return _tokens_used


def _make_client(config: dict) -> Groq:
    return Groq(api_key=os.environ.get("GROQ_API_KEY", ""))


def _llm(client: Groq, config: dict, messages: list, max_tokens: int = 2000) -> tuple[str, int]:
    global _tokens_used

    if _tokens_used >= config["token_budget"]:
        _log("LLM", "BUDGET", "EXHAUSTED", f"{_tokens_used}/{config['token_budget']}", "R")
        return "", 0

    wait = config["rate_limit_wait"]
    for attempt in range(config["rate_limit_retry"]):
        try:
            resp = client.chat.completions.create(
                model=config["model"],
                max_tokens=max_tokens,
                messages=messages,
            )
            toks = getattr(resp.usage, "total_tokens", 0)
            _tokens_used += toks
            return resp.choices[0].message.content.strip(), toks
        except Exception as e:
            err = str(e)
            if "429" in err or "rate_limit" in err.lower():
                _log("LLM", "RETRY", f"Rate limit attempt={attempt+1}", f"waiting {wait}s", "Y")
                time.sleep(wait)
                wait *= 2
            else:
                _log("LLM", "ERROR", "Call failed", err[:200], "R")
                return "", 0

    return "", 0


def _safe_json(text: str) -> dict | list:
    for fence in ["```json", "```"]:
        if fence in text:
            text = text.split(fence, 1)[1].split("```", 1)[0].strip()
            break
    try:
        return json.loads(text)
    except Exception:
        for s, e in [("{", "}"), ("[", "]")]:
            si, ei = text.find(s), text.rfind(e)
            if si != -1 and ei > si:
                try:
                    return json.loads(text[si:ei+1])
                except Exception:
                    pass
    return {"raw": text}
