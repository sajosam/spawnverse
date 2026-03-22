# Architecture

## The Two-Part Agent File

Every generated agent has two parts:

**Part 1 — Stdlib** (written by orchestrator, never by LLM)
- All database helpers: read, write, send, spawn, etc.
- LLM call wrapper: think()
- Progress reporting: progress()
- Agent identity: _ID baked in at generation time

**Part 2 — main()** (written by LLM)
- Task-specific logic only
- Calls stdlib functions
- Cannot import anything else
- Cannot write to other namespaces

This separation means the LLM never sees stdlib code → no escaping bugs.

## Class Overview

```
Orchestrator
  DistributedMemory   spawnverse.db — the shared brain
  VectorDB            ChromaDB — semantic search (optional)
  Guardrails          4-layer safety
  Generator           LLM writes agent main()
  Executor            subprocess with OS limits
  IntentDriftScorer   measures output alignment
  OutputQualityScorer LLM-as-judge on outputs
  SpawnScorer         gates sub-agent requests
```
