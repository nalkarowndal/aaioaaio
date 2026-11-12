"""P6 conversation history: owner-scoped, bounded SQLite persistence.

Never enable the unauthenticated single-user owner on a public deployment.
The database stores chat text, not uploaded file bytes, and is not encrypted.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sqlite3
from uuid import uuid4

MAX_TITLE_CHARS = 90
MAX_MESSAGES = 300
MAX_CONTENT_CHARS = 100_000
MAX_RESULTS = 40


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _clean_title(title: str) -> str:
    if not isinstance(title, str):
        raise ValueError("대화 제목은 문자열이어야 합니다.")
    value = " ".join(title.split()).strip()[:MAX_TITLE_CHARS]
    if not value:
        raise ValueError("대화 제목을 입력해 주세요.")
    return value


def _clean_messages(messages: list[dict]) -> list[dict]:
    if not isinstance(messages, list) or len(messages) > MAX_MESSAGES:
        raise ValueError("저장 가능한 메시지 수를 초과했습니다.")
    result = []
    for message in messages:
        if not isinstance(message, dict) or message.get("role") not in ("user", "assistant"):
            raise ValueError("저장할 수 없는 메시지 형식입니다.")
        content = message.get("content")
        if not isinstance(content, str) or len(content) > MAX_CONTENT_CHARS:
            raise ValueError("메시지 내용이 너무 길거나 잘못되었습니다.")
        result.append({"role": message["role"], "content": content})
    return result


def title_from_messages(messages: list[dict]) -> str:
    for item in messages:
        if item.get("role") == "user" and isinstance(item.get("content"), str):
            title = " ".join(item["content"].split())
            if title:
                return title[:MAX_TITLE_CHARS]
    return "새 대화"


class ConversationStore:
    """Use separate short-lived connections; every query is scoped by owner."""

    def __init__(self, path: Path | str):
        self.path = Path(path)
        self.path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute(
                """CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    owner TEXT NOT NULL,
                    title TEXT NOT NULL,
                    messages_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                )"""
            )
            con.execute(
                "CREATE INDEX IF NOT EXISTS idx_conversations_owner_recent "
                "ON conversations(owner, updated_at DESC)"
            )

    def _connect(self) -> sqlite3.Connection:
        con = sqlite3.connect(self.path, timeout=5)
        con.execute("PRAGMA busy_timeout=5000")
        return con

    @staticmethod
    def _owner(owner: str) -> str:
        if not isinstance(owner, str) or not owner or len(owner) > 256:
            raise ValueError("유효한 대화 소유자가 필요합니다.")
        return owner

    def create(self, owner: str, messages: list[dict] | None = None, title: str | None = None) -> str:
        owner = self._owner(owner)
        safe_messages = _clean_messages(messages if messages is not None else [])
        safe_title = _clean_title(title) if title is not None else title_from_messages(safe_messages)
        conversation_id = uuid4().hex
        timestamp = _now()
        with self._connect() as con:
            con.execute(
                "INSERT INTO conversations (id, owner, title, messages_json, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (conversation_id, owner, safe_title,
                 json.dumps(safe_messages, ensure_ascii=False), timestamp, timestamp),
            )
        return conversation_id

    def get(self, owner: str, conversation_id: str) -> dict | None:
        with self._connect() as con:
            row = con.execute(
                "SELECT id, title, messages_json, created_at, updated_at FROM conversations "
                "WHERE owner=? AND id=?",
                (self._owner(owner), conversation_id),
            ).fetchone()
        if row is None:
            return None
        messages = _clean_messages(json.loads(row[2]))
        return {"id": row[0], "title": row[1], "messages": messages,
                "created_at": row[3], "updated_at": row[4]}

    def list(self, owner: str, query: str = "", limit: int = MAX_RESULTS) -> list[dict]:
        if not 1 <= limit <= MAX_RESULTS:
            raise ValueError("검색 결과 제한이 올바르지 않습니다.")
        query = query.strip()[:120]
        # Literal substring search; %/_ must not become SQL wildcards.
        pattern = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        with self._connect() as con:
            rows = con.execute(
                "SELECT id, title, updated_at FROM conversations "
                "WHERE owner=? AND (title LIKE ? ESCAPE '\\' OR messages_json LIKE ? ESCAPE '\\') "
                "ORDER BY updated_at DESC, id DESC LIMIT ?",
                (self._owner(owner), pattern, pattern, limit),
            ).fetchall()
        return [{"id": row[0], "title": row[1], "updated_at": row[2]} for row in rows]

    def save(self, owner: str, conversation_id: str, messages: list[dict]) -> bool:
        safe_messages = _clean_messages(messages)
        with self._connect() as con:
            cur = con.execute(
                "UPDATE conversations SET messages_json=?, updated_at=? WHERE owner=? AND id=?",
                (json.dumps(safe_messages, ensure_ascii=False), _now(),
                 self._owner(owner), conversation_id),
            )
        return cur.rowcount == 1

    def rename(self, owner: str, conversation_id: str, title: str) -> bool:
        with self._connect() as con:
            cur = con.execute(
                "UPDATE conversations SET title=?, updated_at=? WHERE owner=? AND id=?",
                (_clean_title(title), _now(), self._owner(owner), conversation_id),
            )
        return cur.rowcount == 1

    def delete(self, owner: str, conversation_id: str) -> bool:
        with self._connect() as con:
            cur = con.execute(
                "DELETE FROM conversations WHERE owner=? AND id=?",
                (self._owner(owner), conversation_id),
            )
        return cur.rowcount == 1
