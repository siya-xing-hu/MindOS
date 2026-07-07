"""LLM 基类。"""
from abc import ABC, abstractmethod
from typing import Iterator, Optional


class BaseLLM(ABC):
    def __init__(self, model: str, base_url: Optional[str] = None):
        self.model = model
        self.base_url = base_url

    @abstractmethod
    def stream(self, prompt: str, context: list[dict]) -> Iterator[str]:
        """基于 context（检索结果）流式生成答案，yield 文本块。"""
