"""Small shared constants — single source of truth instead of magic numbers scattered
across models/migrations.
"""

# Dimension of the embeddings stored in `code_list.embedding` and
# `example_memory.embedding`. 1024 matches bge-m3 (Phase 3's chosen embedding model,
# served locally via Ollama — decided 2026-10-13, see CLAUDE.md). No real embeddings
# existed yet when this changed from the earlier OpenAI-sized placeholder (1536), so
# no data was lost.
EMBEDDING_DIM = 1024
