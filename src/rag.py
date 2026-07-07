"""RAG 问答：检索 top-K 作 context，调 LLM 流式生成。"""
from typing import Iterator, Tuple

from .config import RAG_TOP_K
from .kb_registry import get_llm
from .search import search as do_search


def ask(kb_name: str, question: str) -> Tuple[list[dict], Iterator[str]]:
    """返回 (sources, stream_generator)。

    sources: 检索到的 top-K 文档片段，含 title/section/path/text
    stream_generator: LLM 流式输出的文本块迭代器
    """
    results = do_search(kb_name, question, top_k=RAG_TOP_K)
    sources = [
        {
            "title": r["title"],
            "section": r["section"],
            "path": r["path"],
            "text": r["text"],
        }
        for r in results
    ]
    llm = get_llm(kb_name)
    context = [
        {"title": s["title"], "section": s["section"], "text": s["text"]}
        for s in sources
    ]
    return sources, llm.stream(question, context)
