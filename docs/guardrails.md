# Guardrails

## Layer 1 — Code Scan
Runs before subprocess. Blocks: os.system, subprocess,
__import__, eval, exec, open("/etc"), requests.post, socket, os.environ.

## Layer 2 — Budget Enforcer  
Per-agent token limit in stdlib. think() returns empty when exhausted.

## Layer 3 — Output Validator
Before memory write. Checks: not None, not empty, not too large.

## Layer 4 — Semantic (LLM-as-judge)
Reviews for harmful content, PII, misinformation, prompt injection.

## Disable (dev only)
CONFIG["guardrail_code"] = False
CONFIG["guardrail_output"] = False  
CONFIG["guardrail_semantic"] = False
