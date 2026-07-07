"""通用文件读取：扫目录下所有 .md 文件，计算 content hash 作版本。

不依赖 frontmatter，page_id 用文件相对路径的 hash（稳定，不随内容变）。
如果文件有 frontmatter，读取时剥离，不参与切分。
"""
import hashlib
import re
from pathlib import Path

FRONTMATTER_RE = re.compile(r"^---\n.*?\n---\n", re.DOTALL)


def list_files(workspace: str) -> list[str]:
    root = Path(workspace)
    if not root.exists():
        return []
    return sorted(
        str(p.relative_to(root))
        for p in root.rglob("*.md")
        if p.is_file()
    )


def read_file(workspace: str, rel_path: str) -> dict:
    full = Path(workspace) / rel_path
    raw = full.read_text(encoding="utf-8")
    body = FRONTMATTER_RE.sub("", raw, count=1)
    page_id = _hash_str("path:" + rel_path)  # 12 位 hex 字符串，存 Milvus VARCHAR(64)
    content_hash = _hash_int(raw)  # INT64，存 Milvus INT64
    title = full.stem
    return {
        "page_id": page_id,
        "content_hash": content_hash,
        "title": title,
        "text": body,
        "path": rel_path,
    }


def _hash_str(s: str) -> str:
    """page_id 用：12 位 hex 字符串（VARCHAR）。"""
    return hashlib.md5(s.encode()).hexdigest()[:12]


def _hash_int(s: str) -> int:
    """content_hash 用：12 位 hex 转 INT64。"""
    return int(hashlib.md5(s.encode()).hexdigest()[:12], 16)
