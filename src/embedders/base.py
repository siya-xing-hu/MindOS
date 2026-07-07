"""Embedder 基类。"""
from abc import ABC, abstractmethod
from typing import Optional


class BaseEmbedder(ABC):
    def __init__(self, model: str, base_url: Optional[str] = None):
        self.model = model
        self.base_url = base_url

    @abstractmethod
    def dim(self) -> int:
        """返回向量维度，用于 Milvus schema。"""

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """批量向量化。"""
