"""LLM 注册表。"""
from .base import BaseLLM
from .omlx import OmlxLLM

LLMS = {
    "omlx": OmlxLLM,
}
