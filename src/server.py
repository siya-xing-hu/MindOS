"""FastAPI Web 服务：知识库管理 + 三 tab（文档 / 搜索 / 问答）。"""
import json
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from .config import SUPPORTED_EMBEDDERS, SUPPORTED_LLMS, SUPPORTED_SOURCES
from .ingest import get_index_status, ingest_files, refresh_kb
from .kb_registry import (
    create_kb,
    delete_kb,
    get_kb,
    list_kbs,
    update_kb,
)
from .rag import ask as kb_ask
from .search import search as kb_search

app = FastAPI(title="MindOS")
TEMPLATES_DIR = Path(__file__).parent / "templates"


class IngestRequest(BaseModel):
    files: list[str]


class AskRequest(BaseModel):
    question: str


class KBConfig(BaseModel):
    kb_name: str
    display_name: str
    source: str = "file"
    collection: str
    workspace: str
    embedding_provider: str = "omlx"
    embedding_model: str
    embedding_base_url: str | None = None
    llm_provider: str = "omlx"
    llm_model: str
    llm_base_url: str | None = None


class KBUpdate(BaseModel):
    display_name: str | None = None
    source: str | None = None
    collection: str | None = None
    workspace: str | None = None
    embedding_provider: str | None = None
    embedding_model: str | None = None
    embedding_base_url: str | None = None
    llm_provider: str | None = None
    llm_model: str | None = None
    llm_base_url: str | None = None


@app.get("/", response_class=HTMLResponse)
def index():
    return (TEMPLATES_DIR / "index.html").read_text(encoding="utf-8")


@app.get("/api/kbs")
def api_kbs():
    return {"kbs": list_kbs()}


@app.post("/api/kbs")
def api_create_kb(cfg: KBConfig):
    if cfg.source not in SUPPORTED_SOURCES:
        raise HTTPException(400, f"unsupported source: {cfg.source}")
    if cfg.embedding_provider not in SUPPORTED_EMBEDDERS:
        raise HTTPException(400, f"unsupported embedding provider: {cfg.embedding_provider}")
    if cfg.llm_provider not in SUPPORTED_LLMS:
        raise HTTPException(400, f"unsupported llm provider: {cfg.llm_provider}")
    try:
        return create_kb(cfg.model_dump())
    except Exception as e:
        raise HTTPException(400, str(e))


@app.put("/api/kbs/{kb_name}")
def api_update_kb(kb_name: str, cfg: KBUpdate):
    try:
        return update_kb(kb_name, cfg.model_dump(exclude_none=True))
    except KeyError:
        raise HTTPException(404, "KB not found")


@app.delete("/api/kbs/{kb_name}")
def api_delete_kb(kb_name: str):
    if not delete_kb(kb_name):
        raise HTTPException(404, "KB not found")
    return {"ok": True}


@app.post("/api/kbs/{kb_name}/duplicate")
def api_duplicate_kb(kb_name: str, new_name: str):
    """一键复制知识库配置。只复制配置，不复制数据。

    新 KB 的 collection 名自动加后缀，workspace 路径需用户改。
    """
    src = get_kb(kb_name)
    new_cfg = {
        **src,
        "kb_name": new_name,
        "display_name": src["display_name"] + " (copy)",
        "collection": src["collection"] + "_copy",
    }
    new_cfg.pop("created_at", None)
    new_cfg.pop("updated_at", None)
    try:
        return create_kb(new_cfg)
    except Exception as e:
        raise HTTPException(400, str(e))


@app.get("/api/options")
def api_options():
    return {
        "sources": SUPPORTED_SOURCES,
        "embedders": SUPPORTED_EMBEDDERS,
        "llms": SUPPORTED_LLMS,
    }


def _ensure_kb(kb_name: str):
    try:
        get_kb(kb_name)
    except KeyError:
        raise HTTPException(404, "KB not found")


@app.get("/api/{kb}/tree")
def api_tree(kb: str):
    _ensure_kb(kb)
    cfg = get_kb(kb)
    from .file_reader import list_files, read_file

    files = list_files(cfg["workspace"])
    indexed = get_index_status(kb)  # {path: content_hash}

    page_infos = []
    for rel in files:
        try:
            doc = read_file(cfg["workspace"], rel)
            page_infos.append(
                {
                    "path": rel,
                    "content_hash": doc["content_hash"],
                    "title": doc["title"],
                }
            )
        except Exception:
            page_infos.append({"path": rel, "content_hash": 0, "title": ""})

    tree = _build_tree(page_infos, indexed)
    return {"tree": tree}


@app.get("/api/{kb}/file")
def api_file(kb: str, path: str):
    _ensure_kb(kb)
    cfg = get_kb(kb)
    full = Path(cfg["workspace"]) / path
    if not full.exists() or not full.is_file():
        raise HTTPException(404, "File not found")
    return {"content": full.read_text(encoding="utf-8")}


@app.post("/api/{kb}/ingest")
def api_ingest(kb: str, req: IngestRequest):
    _ensure_kb(kb)
    return ingest_files(kb, req.files)


@app.post("/api/{kb}/refresh")
def api_refresh(kb: str):
    _ensure_kb(kb)
    return refresh_kb(kb)


@app.get("/api/{kb}/search")
def api_search(kb: str, q: str, top: int = 10):
    _ensure_kb(kb)
    return {"results": kb_search(kb, q, top_k=top)}


@app.post("/api/{kb}/ask")
def api_ask(kb: str, req: AskRequest):
    _ensure_kb(kb)

    def stream():
        sources, gen = kb_ask(kb, req.question)
        yield f"data: {json.dumps({'type': 'sources', 'data': sources}, ensure_ascii=False)}\n\n"
        for chunk in gen:
            yield f"data: {json.dumps({'type': 'token', 'data': chunk}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream")


def _build_tree(file_infos: list[dict], indexed: dict) -> dict:
    root: dict = {"name": "", "children": {}, "files": []}
    for info in file_infos:
        parts = info["path"].split("/")
        node = root
        for p in parts[:-1]:
            if p not in node["children"]:
                node["children"][p] = {"name": p, "children": {}, "files": []}
            node = node["children"][p]
        status = "unindexed"
        path = info["path"]
        if path in indexed:
            if indexed[path] == info["content_hash"]:
                status = "current"
            else:
                status = "stale"
        node["files"].append(
            {
                "name": parts[-1],
                "path": info["path"],
                "status": status,
                "title": info.get("title", ""),
            }
        )
    return root


def main():
    import uvicorn

    uvicorn.run("src.server:app", host="0.0.0.0", port=9000, reload=False)


if __name__ == "__main__":
    main()
