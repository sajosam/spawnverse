# spawnverse/vectordb/store.py
import os
import json
import hashlib

from ..display import _log


class VectorDB:
    """
    Optional ChromaDB-backed RAG store.
    Silently disabled when vector_db_enabled=False or chromadb is not installed.
    Three collections: knowledge (ingested docs), fossils (agent outputs), context (runtime).
    """

    def __init__(self, config: dict) -> None:
        self.cfg    = config
        self._ready = False

        if not config["vector_db_enabled"]:
            return

        try:
            import chromadb
            self._chroma    = chromadb.PersistentClient(path=config["vector_db_path"])
            self._knowledge = self._chroma.get_or_create_collection(
                "sv_knowledge", metadata={"hnsw:space": "cosine"})
            self._fossils   = self._chroma.get_or_create_collection(
                "sv_fossils", metadata={"hnsw:space": "cosine"})
            self._context   = self._chroma.get_or_create_collection(
                "sv_context", metadata={"hnsw:space": "cosine"})
            self._ready     = True
            _log("VDB", "CHROMADB", "READY",
                 f"knowledge={self._knowledge.count()} fossils={self._fossils.count()}", "G")
        except ImportError:
            _log("VDB", "WARN", "chromadb not installed — RAG disabled", "", "Y")

    # ── ingestion ─────────────────────────────────────────────────────

    def ingest(self, source: str, metadata: dict = None) -> None:
        if not self._ready:
            return
        text = source
        if os.path.isfile(source):
            try:
                with open(source, encoding="utf-8", errors="ignore") as f:
                    text = f.read()
            except Exception as e:
                _log("VDB", "INGEST", "Read failed", str(e), "Y")
                return

        chunks = self._chunk(text)
        ids, docs, metas = [], [], []
        for i, chunk in enumerate(chunks):
            ids.append(hashlib.md5(f"{str(source)[:40]}_{i}".encode()).hexdigest())
            docs.append(chunk)
            metas.append({"source": str(source)[:100], "chunk": i, **(metadata or {})})
        try:
            self._knowledge.upsert(documents=docs, ids=ids, metadatas=metas)
        except Exception as e:
            _log("VDB", "INGEST", "Failed", str(e), "R")

    def index_output(self, agent_id: str, role: str, output, task_type: str) -> None:
        if not self._ready:
            return
        text   = f"role:{role}\ntask:{task_type}\n{json.dumps(output)[:1200]}"
        chunks = self._chunk(text)
        ids, docs, metas = [], [], []
        for i, ch in enumerate(chunks):
            ids.append(hashlib.md5(f"fossil_{agent_id}_{i}".encode()).hexdigest())
            docs.append(ch)
            metas.append({"source": f"fossil:{agent_id}", "agent_id": agent_id, "role": role})
        try:
            self._fossils.upsert(documents=docs, ids=ids, metadatas=metas)
        except Exception:
            pass

    # ── retrieval ─────────────────────────────────────────────────────

    def search(self, query: str, n: int = None, collection: str = "knowledge") -> list:
        if not self._ready:
            return []
        n   = n or self.cfg["rag_top_k"]
        col = {"knowledge": self._knowledge,
               "fossils":   self._fossils,
               "context":   self._context}.get(collection, self._knowledge)
        if col.count() == 0:
            return []
        try:
            res   = col.query(query_texts=[query], n_results=min(n, col.count()))
            docs  = res.get("documents", [[]])[0]
            dists = res.get("distances",  [[]])[0]
            metas = res.get("metadatas",  [[]])[0]
            return [{"text": d, "score": round(1 - s, 3), "source": m.get("source", "")}
                    for d, s, m in zip(docs, dists, metas)]
        except Exception as e:
            _log("VDB", "SEARCH", "Failed", str(e), "R")
            return []

    def context_string(self, query: str, collection: str = "knowledge") -> str:
        hits = self.search(query, collection=collection)
        if not hits:
            return "No relevant context found."
        return "\n\n".join(
            f"[{i+1}] score={h['score']} src={h['source']}\n{h['text']}"
            for i, h in enumerate(hits)
        )

    # ── internal ──────────────────────────────────────────────────────

    def _chunk(self, text: str) -> list:
        size, lap = self.cfg["rag_chunk_size"], self.cfg["rag_chunk_overlap"]
        chunks, i = [], 0
        while i < len(text):
            chunks.append(text[i:i + size])
            i += size - lap
        return chunks
