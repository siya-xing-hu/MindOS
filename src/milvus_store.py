"""Milvus 多 collection 管理。每个知识库一个 collection。"""
from typing import Optional

from pymilvus import DataType, MilvusClient

from .config import MILVUS_URI


class MilvusStore:
    def __init__(self, collection: str, dim: int):
        self.client = MilvusClient(uri=MILVUS_URI)
        self.collection = collection
        self.dim = dim
        self._ensure_collection()

    def _ensure_collection(self):
        if self.client.has_collection(self.collection):
            self.client.load_collection(self.collection)
            return

        schema = self.client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("pk", DataType.VARCHAR, max_length=128, is_primary=True)
        schema.add_field("page_id", DataType.VARCHAR, max_length=64)
        schema.add_field("content_hash", DataType.INT64)
        schema.add_field("title", DataType.VARCHAR, max_length=512)
        schema.add_field("section", DataType.VARCHAR, max_length=1024)
        schema.add_field("path", DataType.VARCHAR, max_length=1024)
        schema.add_field("chunk_idx", DataType.INT64)
        schema.add_field("text", DataType.VARCHAR, max_length=8192)
        schema.add_field("vector", DataType.FLOAT_VECTOR, dim=self.dim)

        self.client.create_collection(collection_name=self.collection, schema=schema)

        index_params = self.client.prepare_index_params()
        index_params.add_index(
            field_name="vector",
            index_type="HNSW",
            metric_type="IP",
            params={"M": 16, "efConstruction": 200},
        )
        self.client.create_index(
            collection_name=self.collection, index_params=index_params
        )
        self.client.load_collection(self.collection)

    def delete_by_page(self, page_id: str):
        self.client.delete(
            collection_name=self.collection,
            filter=f'page_id == "{page_id}"',
        )

    def delete_by_paths(self, paths: list[str]):
        if not paths:
            return
        for path in paths:
            self.client.delete(
                collection_name=self.collection,
                filter=f'path == "{path}"',
            )

    def upsert_chunks(self, chunks: list[dict]):
        if not chunks:
            return
        self.client.upsert(collection_name=self.collection, data=chunks)

    def search(
        self, vector: list[float], top_k: int = 10, filter_expr: Optional[str] = None
    ) -> list[dict]:
        results = self.client.search(
            collection_name=self.collection,
            data=[vector],
            limit=top_k,
            output_fields=[
                "page_id",
                "content_hash",
                "title",
                "section",
                "path",
                "chunk_idx",
                "text",
            ],
            filter=filter_expr or "",
        )
        out = []
        if not results:
            return out
        for hit in results[0]:
            e = hit.get("entity", {})
            out.append(
                {
                    "score": hit.get("distance", 0.0),
                    "page_id": e.get("page_id"),
                    "content_hash": e.get("content_hash"),
                    "title": e.get("title"),
                    "section": e.get("section"),
                    "path": e.get("path"),
                    "chunk_idx": e.get("chunk_idx"),
                    "text": e.get("text"),
                }
            )
        return out

    def list_indexed(self) -> dict:
        """返回 {path: content_hash}，用于实时比对入库状态。"""
        out: dict = {}
        offset = 0
        batch = 1000
        while True:
            res = self.client.query(
                collection_name=self.collection,
                filter="",
                output_fields=["path", "content_hash"],
                limit=batch,
                offset=offset,
            )
            if not res:
                break
            for r in res:
                out[r["path"]] = r["content_hash"]
            if len(res) < batch:
                break
            offset += batch
        return out
