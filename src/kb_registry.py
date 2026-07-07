"""从 SQLite 加载 KB 配置，按需装配 embedder / llm / milvus store。

不再有 adapter 抽象——所有数据源都用 file_reader（扫目录下 .md）。

embedder / llm / milvus 实例按 kb_name 缓存，避免每次请求都重连 Milvus。
KB 配置变更（create/update/delete）时清缓存。
"""
import threading

from .embedders import EMBEDDERS
from .embedders.base import BaseEmbedder
from .kb_store import KBStore
from .llms import LLMS
from .llms.base import BaseLLM
from .milvus_store import MilvusStore

_store = KBStore()

_lock = threading.Lock()
_embedder_cache: dict[str, BaseEmbedder] = {}
_llm_cache: dict[str, BaseLLM] = {}
_milvus_cache: dict[str, MilvusStore] = {}


def _invalidate(kb_name: str):
    """KB 配置变更时调用，清掉该 KB 的所有缓存实例。"""
    with _lock:
        _embedder_cache.pop(kb_name, None)
        _llm_cache.pop(kb_name, None)
        _milvus_cache.pop(kb_name, None)


def list_kbs() -> list[dict]:
    return _store.list_kbs()


def get_kb(kb_name: str) -> dict:
    kb = _store.get_kb(kb_name)
    if not kb:
        raise KeyError(f"unknown knowledge base: {kb_name}")
    return kb


def create_kb(kb: dict) -> dict:
    return _store.create_kb(kb)


def update_kb(kb_name: str, kb: dict) -> dict:
    updated = _store.update_kb(kb_name, kb)
    if not updated:
        raise KeyError(f"unknown knowledge base: {kb_name}")
    _invalidate(kb_name)
    return updated


def delete_kb(kb_name: str) -> bool:
    ok = _store.delete_kb(kb_name)
    if ok:
        _invalidate(kb_name)
    return ok


def get_embedder(kb_name: str) -> BaseEmbedder:
    with _lock:
        if kb_name in _embedder_cache:
            return _embedder_cache[kb_name]
    cfg = get_kb(kb_name)
    embedder = EMBEDDERS[cfg["embedding_provider"]](
        model=cfg["embedding_model"], base_url=cfg.get("embedding_base_url")
    )
    with _lock:
        # 双检：并发时另一个线程可能已经建过
        if kb_name not in _embedder_cache:
            _embedder_cache[kb_name] = embedder
        return _embedder_cache[kb_name]


def get_llm(kb_name: str) -> BaseLLM:
    with _lock:
        if kb_name in _llm_cache:
            return _llm_cache[kb_name]
    cfg = get_kb(kb_name)
    llm = LLMS[cfg["llm_provider"]](
        model=cfg["llm_model"], base_url=cfg.get("llm_base_url")
    )
    with _lock:
        if kb_name not in _llm_cache:
            _llm_cache[kb_name] = llm
        return _llm_cache[kb_name]


def get_milvus(kb_name: str) -> MilvusStore:
    with _lock:
        if kb_name in _milvus_cache:
            return _milvus_cache[kb_name]
    cfg = get_kb(kb_name)
    embedder = get_embedder(kb_name)
    store = MilvusStore(cfg["collection"], embedder.dim())
    with _lock:
        if kb_name not in _milvus_cache:
            _milvus_cache[kb_name] = store
        return _milvus_cache[kb_name]
