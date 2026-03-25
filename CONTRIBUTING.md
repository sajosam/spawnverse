# Contributing to SpawnVerse 🚀

Thanks for your interest in contributing — this project is built to be simple, hackable, and evolving.

---

## 🧭 Where You Can Help

| Area | What's needed |
|------|--------------|
| 🧪 Tests | Unit tests for DistributedMemory, Guardrails, SpawnScorer |
| 🐳 Sandbox | Replace subprocess with Docker-based isolation |
| 🧠 Intent Drift | Explore embedding-based scoring (sentence-transformers) |
| 📦 Examples | Healthcare, code review, content calendar |
| 🪟 Windows | Fix resource limits on Windows |

---

## ⚡ Quick Start

```bash
git clone https://github.com/sajosam/spawnverse
cd spawnverse
pip install -e ".[dev]"
```

Run a simple example:

```python
from spawnverse import Orchestrator

Orchestrator().run({
    "description": "Research top 5 EVs in India under ₹25L"
})
```

---

## 🛠️ How to Contribute

1. Fork the repo  
2. Create a branch (`feature/your-feature`)  
3. Make your changes  
4. Open a PR  

---

## 📌 Contribution Guidelines

- Keep it simple (avoid over-engineering)
- Prefer clarity over cleverness
- Add logs where useful
- If possible, include a test
- Small PRs > large PRs

---

## 💡 Good First Issues

Look for issues labeled:
- `good first issue`
- `enhancement`

Or improve:
- logging
- error handling
- examples

---

## 🤝 Before You Start

If you're working on something large (DAG, Soul system, etc.),  
drop a comment on the issue first — happy to discuss direction.
