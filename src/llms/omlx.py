"""走 oMLX /v1/chat/completions 的 LLM（流式）。"""
import json
from typing import Iterator

import requests

from .base import BaseLLM

SYSTEM_PROMPT = (
    "你是一个知识库助手，基于给定的参考资料回答用户问题。"
    "如果资料中没有答案，请明确说明资料不足，不要编造。"
    "回答末尾用【来源 N】标注引用的参考资料编号。"
)


class OmlxLLM(BaseLLM):
    def stream(self, prompt: str, context: list[dict]) -> Iterator[str]:
        ctx_text = "\n\n".join(
            f"【来源 {i + 1}】{c.get('title', '')} > {c.get('section', '')}\n{c.get('text', '')}"
            for i, c in enumerate(context)
        )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {
                "role": "user",
                "content": f"参考资料:\n{ctx_text}\n\n用户问题: {prompt}",
            },
        ]
        r = requests.post(
            f"{self.base_url}/v1/chat/completions",
            json={"model": self.model, "messages": messages, "stream": True},
            stream=True,
            timeout=600,
        )
        r.raise_for_status()
        for raw in r.iter_lines():
            if not raw:
                continue
            line = raw.decode("utf-8")
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            try:
                d = json.loads(payload)
            except json.JSONDecodeError:
                continue
            delta = d.get("choices", [{}])[0].get("delta", {}).get("content", "")
            if delta:
                yield delta
