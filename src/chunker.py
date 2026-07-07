"""Markdown header-aware 切分。

设计要点：
- 标题只用于跟踪 section 路径（如「广发银行 > 0.1.0 > 接口说明」），不触发断点。
  避免密集小标题把文档碎成片。
- 每个 chunk 都带完整标题链：标题行本身留在正文里（确保 LLM 看到），
  section 字段记录祖先标题路径（用于检索展示和过滤）。
- buffer 累积到 chunk_size（字符数）才断，断点尽量选空行处，避免切断段落。
- overlap 默认 0：不重复内容。上下文靠标题链保证，而非靠 chunk 间重叠。
- plantuml / 代码块作为整体不拆分。
- 过短的 chunk（< min_chunk_size）合并到上一个，避免碎片。
"""
import re
from typing import List

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+)$")
FENCE_RE = re.compile(r"^```")


def chunk_markdown(
    text: str,
    chunk_size: int = 1500,
    overlap: int = 0,
    min_chunk_size: int = 200,
) -> List[dict]:
    lines = text.split("\n")
    chunks: list[dict] = []
    current_section: list[str] = []
    buffer: list[str] = []
    buffer_len = 0
    in_fence = False
    # 记录当前 chunk 起始时的 section，断 chunk 时定格
    chunk_section: list[str] = []

    def buffer_char_len(buf: list[str]) -> int:
        return sum(len(l) + 1 for l in buf)

    def section_str(sec: list[str]) -> str:
        return " > ".join(s for s in sec if s) or "(root)"

    def flush(overlap_chars: int):
        nonlocal buffer, buffer_len, chunk_section
        if not buffer:
            return
        body = "\n".join(buffer).strip()
        if body:
            chunks.append(
                {
                    "section": section_str(chunk_section),
                    "text": body,
                }
            )
        # 留 overlap 字符作为下一段开头
        if overlap_chars > 0 and buffer_char_len(buffer) > overlap_chars:
            tail: list[str] = []
            acc = 0
            for line in reversed(buffer):
                if acc + len(line) + 1 > overlap_chars and tail:
                    break
                tail.insert(0, line)
                acc += len(line) + 1
            buffer = tail
            buffer_len = buffer_char_len(buffer)
        else:
            buffer = []
            buffer_len = 0

    def _buffer_has_content() -> bool:
        return any(l.strip() for l in buffer)

    for line in lines:
        # 新 chunk 起点快照 section（buffer 无实际内容时才更新）
        if not _buffer_has_content():
            chunk_section = list(current_section)

        if FENCE_RE.match(line):
            in_fence = not in_fence
            buffer.append(line)
            buffer_len += len(line) + 1
            continue

        if not in_fence:
            m = HEADING_RE.match(line)
            if m:
                level = len(m.group(1))
                heading = m.group(2).strip()
                while len(current_section) >= level:
                    current_section.pop()
                while len(current_section) < level - 1:
                    current_section.append("")
                if len(current_section) == level - 1:
                    current_section.append(heading)
                else:
                    current_section[level - 1] = heading
                # 标题进入「无内容」buffer 时，section 用更新后的路径
                if not _buffer_has_content():
                    chunk_section = list(current_section)
                buffer.append(line)
                buffer_len += len(line) + 1
                continue

        buffer.append(line)
        buffer_len += len(line) + 1

        # 超过 chunk_size 时，尽量在空行处断开，避免切段落
        if not in_fence and buffer_len >= chunk_size:
            # 回退到最后一个空行（保留至少一半内容才断，否则直接断）
            cut = _find_break_point(buffer, min_keep=chunk_size // 2)
            if cut is not None and cut > 0:
                to_flush = buffer[:cut]
                rest = buffer[cut:]
                buffer = to_flush
                buffer_len = buffer_char_len(to_flush)
                flush(overlap)
                buffer = rest + buffer  # rest + overlap 尾部
                buffer_len = buffer_char_len(buffer)
                # 新 chunk 起点重置 section（rest 里的内容属于当前 section）
                chunk_section = list(current_section)
            else:
                flush(overlap)
                chunk_section = list(current_section)

    flush(0)

    # 合并过短的 chunk
    _merge_small_chunks(chunks, min_chunk_size, chunk_size)

    for i, c in enumerate(chunks):
        c["chunk_idx"] = i
    return chunks


def _find_break_point(buffer: list[str], min_keep: int) -> int | None:
    """在 buffer 中找最后一个空行位置作为断点，保证前半段至少 min_keep 字符。"""
    acc = 0
    last_blank = None
    for i, line in enumerate(buffer):
        if line.strip() == "" and acc >= min_keep:
            last_blank = i
        acc += len(line) + 1
    return last_blank


def _merge_small_chunks(
    chunks: list[dict], min_size: int, max_size: int
) -> None:
    """把过短的 chunk 合并到前一个；若前一个合并后会超 max_size，则不合并。"""
    if len(chunks) < 2:
        return
    merged: list[dict] = [chunks[0]]
    for c in chunks[1:]:
        if (
            len(c["text"]) < min_size
            and len(merged[-1]["text"]) + len(c["text"]) + 2 <= max_size * 1.5
        ):
            prev = merged[-1]
            prev["text"] = prev["text"] + "\n\n" + c["text"]
            # section 取合并后首个 chunk 的（更稳定）
        else:
            merged.append(c)
    chunks.clear()
    chunks.extend(merged)
