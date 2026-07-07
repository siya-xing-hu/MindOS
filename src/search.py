"""语义检索。"""
from .config import SEARCH_TOP_K
from .kb_registry import get_embedder, get_milvus


def search(kb_name: str, query: str, top_k: int = SEARCH_TOP_K) -> list[dict]:
    embedder = get_embedder(kb_name)
    store = get_milvus(kb_name)
    vec = embedder.embed([query])[0]
    return store.search(vec, top_k=top_k)
