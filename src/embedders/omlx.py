"""走 oMLX /v1/embeddings 的 embedder（bge-m3-mlx-fp16 等）。"""
import requests

from .base import BaseEmbedder


class OmlxEmbedder(BaseEmbedder):
    def dim(self) -> int:
        # bge-m3-mlx-fp16 是 1024 维。如果换其他模型，按实际维度调整。
        # 未来可改为从 /v1/models 查询自动获取。
        return 1024

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        r = requests.post(
            f"{self.base_url}/v1/embeddings",
            json={"model": self.model, "input": texts},
            timeout=180,
        )
        r.raise_for_status()
        data = r.json()
        return [
            d["embedding"]
            for d in sorted(data["data"], key=lambda x: x["index"])
        ]
