"""Embedder 注册表。"""
from .base import BaseEmbedder
from .omlx import OmlxEmbedder

EMBEDDERS = {
    "omlx": OmlxEmbedder,
}
