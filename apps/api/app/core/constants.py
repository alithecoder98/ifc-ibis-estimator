"""Small shared constants — single source of truth instead of magic numbers scattered
across models/migrations.
"""

# Dimension of the embeddings stored in `code_list.embedding` and
# `example_memory.embedding`. 1536 matches common OpenAI embedding models
# (text-embedding-3-small/ada-002); revisit once the LLM/embedding provider is picked
# (Phase 3) — changing this later means a migration that drops and recreates the vector
# columns, so better to confirm it before any real embeddings are written.
EMBEDDING_DIM = 1536
