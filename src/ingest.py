"""入库流程：手动导入 + refresh。

不依赖 SQLite 状态表——入库状态实时从 Milvus 查 (path, content_hash) 比对。
"""
from .chunker import chunk_markdown
from .config import CHUNK_OVERLAP, CHUNK_SIZE
from .file_reader import list_files, read_file
from .kb_registry import get_embedder, get_kb, get_milvus


def ingest_files(kb_name: str, files: list[str]) -> dict:
    """导入选中的文件。content_hash 不变的跳过，变了或新文件重新入库。"""
    ws = get_kb(kb_name)["workspace"]
    embedder = get_embedder(kb_name)
    store = get_milvus(kb_name)
    indexed = store.list_indexed()  # {path: content_hash}

    added = updated = skipped = failed = 0

    for rel_path in files:
        try:
            doc = read_file(ws, rel_path)
        except Exception as e:
            print(f"! read failed {rel_path}: {e}")
            failed += 1
            continue

        page_id = doc["page_id"]
        content_hash = doc["content_hash"]

        if rel_path in indexed and indexed[rel_path] == content_hash:
            skipped += 1
            continue

        store.delete_by_page(page_id)
        chunks = chunk_markdown(doc["text"], CHUNK_SIZE, CHUNK_OVERLAP)
        if not chunks:
            skipped += 1
            continue

        try:
            vectors = embedder.embed([c["text"] for c in chunks])
        except Exception as e:
            print(f"! embed failed {rel_path}: {e}")
            failed += 1
            continue

        records = []
        for c, v in zip(chunks, vectors):
            records.append(
                {
                    "pk": f"{page_id}:{c['chunk_idx']}",
                    "page_id": page_id,
                    "content_hash": content_hash,
                    "title": doc["title"][:500],
                    "section": c["section"][:1000],
                    "path": rel_path,
                    "chunk_idx": c["chunk_idx"],
                    "text": c["text"][:8000],
                    "vector": v,
                }
            )
        store.upsert_chunks(records)

        if rel_path in indexed:
            updated += 1
        else:
            added += 1

    return {"added": added, "updated": updated, "skipped": skipped, "failed": failed}


def refresh_kb(kb_name: str) -> dict:
    """扫描所有已入库文件，更新 content_hash 变了的，删除本地已不存在的。"""
    ws = get_kb(kb_name)["workspace"]
    store = get_milvus(kb_name)
    indexed = store.list_indexed()  # {path: content_hash}

    local_files = set(list_files(ws))
    indexed_paths = set(indexed.keys())

    deleted_paths = indexed_paths - local_files
    for path in deleted_paths:
        store.delete_by_paths([path])
    deleted = len(deleted_paths)

    to_update = []
    for path in local_files & indexed_paths:
        try:
            doc = read_file(ws, path)
        except Exception:
            continue
        if doc["content_hash"] != indexed[path]:
            to_update.append(path)

    new_files = list(local_files - indexed_paths)
    result = ingest_files(kb_name, to_update + new_files)

    return {
        "added": result["added"],
        "updated": result["updated"],
        "skipped": result["skipped"],
        "failed": result["failed"],
        "deleted": deleted,
    }


def get_index_status(kb_name: str) -> dict:
    """返回 {path: content_hash}，前端用于实时比对三色状态。"""
    store = get_milvus(kb_name)
    return store.list_indexed()
