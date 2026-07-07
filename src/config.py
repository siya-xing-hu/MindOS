"""全局配置：数据目录、Milvus、oMLX、切分参数。

知识库实例配置存 SQLite（见 kb_store.py），不在这里硬编码。
"""
import os
from pathlib import Path

DATA_DIR = Path(os.environ.get("SIYA_DATA_DIR", os.path.expanduser("~/data/siya_kb")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

MILVUS_HOST = os.environ.get("MILVUS_HOST", "localhost")
MILVUS_PORT = int(os.environ.get("MILVUS_PORT", "19530"))
MILVUS_URI = f"http://{MILVUS_HOST}:{MILVUS_PORT}"

SQLITE_PATH = os.environ.get(
    "MINDOS_SQLITE_PATH", str(DATA_DIR / ".mindos.sqlite")
)

OMLX_BASE_URL = os.environ.get("OMLX_BASE_URL", "http://localhost:8000")

CHUNK_SIZE = int(os.environ.get("MINDOS_CHUNK_SIZE", "1500"))
CHUNK_OVERLAP = int(os.environ.get("MINDOS_CHUNK_OVERLAP", "0"))
SEARCH_TOP_K = int(os.environ.get("MINDOS_SEARCH_TOP_K", "10"))
RAG_TOP_K = int(os.environ.get("MINDOS_RAG_TOP_K", "5"))

SUPPORTED_SOURCES = ["file"]
SUPPORTED_EMBEDDERS = ["omlx"]
SUPPORTED_LLMS = ["omlx"]
