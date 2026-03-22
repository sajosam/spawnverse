# Memory Model

READ  → any agent reads any namespace
WRITE → agents write ONLY to their own namespace

## Enforcement

1. At code-generation time: write() has no "namespace" parameter.
   It always uses _ID (baked in at birth). Structurally impossible to write elsewhere.

2. At DB layer: DistributedMemory.write() checks caller_id == owner.

## Namespaces

| Namespace    | Writer       | Contents                     |
|---|---|---|
| system       | Orchestrator | task, config, plan           |
| flight_agent | flight_agent | its result, context, log     |
| hotel_agent  | hotel_agent  | its result, context, log     |
| messages     | append-only  | all agent messages           |
| spawns       | append-only  | sub-agent requests           |
