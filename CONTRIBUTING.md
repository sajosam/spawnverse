# Contributing to SpawnVerse

## Priority Areas

| Area | What's needed |
|---|---|
| Tests | Unit tests for DistributedMemory, Guardrails, SpawnScorer |
| Docker | Replace subprocess with Docker sandbox per agent |
| Intent Drift | sentence-transformers instead of LLM-as-judge |
| Examples | Healthcare, code review, content calendar |
| Windows | Resource limits don't work on Windows yet |

## Quick Setup

```bash
git clone https://github.com/sajosam/spawnverse
cd spawnverse
pip install -e ".[dev]"
```

## Submit a PR

1. Fork → branch → change → PR
2. Add a test if possible
3. Clear description of what and why

## Questions

Open a GitHub Discussion. No question is too basic.
