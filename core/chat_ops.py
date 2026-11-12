"""Pure P7 chat-turn operations, independent of Streamlit and Groq."""
from __future__ import annotations

from typing import Iterable

MAX_EDIT_CHARS = 12_000
MAX_RESPONSE_CHARS = 100_000
ATTACHMENT_MARKER = "\n\n첨부: "


def editable_question_text(content: str) -> str:
    """Do not seed the editor with stale attachment names from the display."""
    return content.split(ATTACHMENT_MARKER, 1)[0] if isinstance(content, str) else ""



def edit_user_message(history: list[dict], index: int, new_text: str) -> list[dict]:
    """Edit a user turn and invalidate all downstream assistant/user turns."""
    if not isinstance(index, int) or index < 0 or index >= len(history):
        raise ValueError("수정할 질문이 없습니다.")
    if history[index].get("role") != "user":
        raise ValueError("사용자 메시지만 수정할 수 있습니다.")
    if not isinstance(new_text, str):
        raise ValueError("질문은 문자열이어야 합니다.")
    question = new_text.strip()
    if not question or len(question) > MAX_EDIT_CHARS:
        raise ValueError("질문은 1~12,000자로 입력해 주세요.")
    # Do not silently preserve obsolete file references when editing a turn.
    return [{"role": msg["role"], "content": msg["content"]} for msg in history[:index]] + [
        {"role": "user", "content": question}
    ]


def regenerate_source(history: list[dict], index: int) -> tuple[list[dict], str]:
    """Return context and user text for an assistant turn, without later turns.

    Attachment bytes are not persisted by P6. Refuse to regenerate from a
    filename-only display marker because that would misrepresent the old prompt.
    """
    if not isinstance(index, int) or index < 1 or index >= len(history):
        raise ValueError("재생성할 답변이 없습니다.")
    if history[index].get("role") != "assistant":
        raise ValueError("AI 답변만 다시 생성할 수 있습니다.")
    preceding = history[:index]
    if not preceding or preceding[-1].get("role") != "user":
        raise ValueError("해당 답변의 질문을 찾지 못했습니다.")
    question = preceding[-1].get("content", "")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("원래 질문을 찾지 못했습니다.")
    if ATTACHMENT_MARKER in question:
        raise ValueError("파일이 첨부된 질문은 원본 파일을 다시 첨부해 요청해 주세요.")
    return preceding, question.strip()


def stream_text_chunks(chunks: Iterable, *, max_chars: int = MAX_RESPONSE_CHARS):
    """Yield only textual ChatCompletion deltas, bounded for SQLite safety.

    Errors during iteration propagate to the caller. Do not commit partial text.
    """
    total = 0
    for chunk in chunks:
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue
        delta = getattr(choices[0], "delta", None)
        text = getattr(delta, "content", None)
        if not isinstance(text, str) or not text:
            continue
        total += len(text)
        if total > max_chars:
            raise ValueError("답변 길이가 저장 가능한 한도를 초과했습니다.")
        yield text
