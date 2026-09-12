# vector_db/ — Embedding + Search Layer

Semantic search, cross-site clustering, and RAG over deviation reports and observations.

## Files

- `embed.py` — Chunks deviation reports and observations, generates embeddings for vector storage.
- `search.py` — Semantic search over past findings ("show me everywhere rebar spacing looks off") and RAG query answering ("what changed since Thursday?").
- `cluster.py` — Cross-site clustering (k-means/DBSCAN on deviation vectors) to surface recurring failure patterns.

## Backend

pgvector (Postgres) for v1 — simplest setup, easy to migrate to Qdrant later if needed.
