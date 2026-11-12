"""P6 SQLite history regression tests, without Streamlit or an external API."""
import pytest

from core.conversations import ConversationStore, MAX_MESSAGES, title_from_messages


def test_store_restores_after_new_process_like_reopen(tmp_path):
    path = tmp_path / "history.sqlite3"
    one = ConversationStore(path)
    first = [
        {"role": "user", "content": "한글 검색 테스트"},
        {"role": "assistant", "content": "알겠습니다"},
    ]
    cid = one.create("account:one", first)
    assert one.get("account:one", cid)["messages"] == first
    del one
    two = ConversationStore(path)
    assert two.get("account:one", cid)["messages"] == first
    assert two.list("account:one", query="한글")[0]["id"] == cid


def test_owner_isolation_for_all_operations(tmp_path):
    db = ConversationStore(tmp_path / "history.sqlite3")
    cid = db.create("alice", [{"role": "user", "content": "비밀 정보"}])
    assert db.get("bob", cid) is None
    assert db.list("bob", query="비밀") == []
    assert db.save("bob", cid, [{"role": "user", "content": "침범"}]) is False
    assert db.rename("bob", cid, "침범") is False
    assert db.delete("bob", cid) is False
    assert db.get("alice", cid)["messages"][0]["content"] == "비밀 정보"


def test_search_is_literal_and_matches_title_and_contents(tmp_path):
    db = ConversationStore(tmp_path / "history.sqlite3")
    cid = db.create("owner", [{"role": "user", "content": "정상 %_ literal 테스트"}])
    db.rename("owner", cid, "개발 관련 내용")
    assert db.list("owner", "개발")[0]["id"] == cid
    assert db.list("owner", "literal")[0]["id"] == cid
    assert db.list("owner", "%_")[0]["id"] == cid
    assert db.list("owner", "없는검색") == []
    assert db.list("owner", "_다른_") == []
    with pytest.raises(ValueError):
        db.list("owner", limit=500)


def test_rename_delete_and_no_resurrection(tmp_path):
    db = ConversationStore(tmp_path / "history.sqlite3")
    cid = db.create("owner", [{"role": "user", "content": "첫 질문"}])
    assert db.rename("owner", cid, " 새 이름 ") is True
    assert db.get("owner", cid)["title"] == "새 이름"
    assert db.save("owner", cid, [{"role": "assistant", "content": "저장된 응답"}])
    assert db.get("owner", cid)["messages"][0]["content"] == "저장된 응답"
    assert db.delete("owner", cid) is True
    assert db.get("owner", cid) is None
    assert db.save("owner", cid, []) is False
    assert db.list("owner") == []


def test_invalid_titles_and_message_payloads_rejected(tmp_path):
    db = ConversationStore(tmp_path / "history.sqlite3")
    with pytest.raises(ValueError):
        db.create("owner", [], title="  ")
    with pytest.raises(ValueError):
        db.create("", [])
    with pytest.raises(ValueError):
        db.create("owner", [{"role": "system", "content": "injection"}])
    with pytest.raises(ValueError):
        db.create("owner", [{"role": "user", "content": "x" * 100_001}])
    with pytest.raises(ValueError):
        db.create("owner", [{"role": "user", "content": "x"}] * (MAX_MESSAGES + 1))


def test_non_chat_metadata_and_upload_bytes_are_not_saved(tmp_path):
    db = ConversationStore(tmp_path / "history.sqlite3")
    cid = db.create("owner", [
        {"role": "user", "content": "파일명: image.png",
         "attachment_bytes": b"never-store", "api_key": "fake-key"},
    ])
    restored = db.get("owner", cid)["messages"]
    assert restored == [{"role": "user", "content": "파일명: image.png"}]
    data = (tmp_path / "history.sqlite3").read_bytes()
    assert b"never-store" not in data and b"fake-key" not in data


def test_title_fallback():
    assert title_from_messages([{"role": "assistant", "content": "환영합니다"}]) == "새 대화"
    assert title_from_messages([{"role": "user", "content": "   한국어  질문  "}]) == "한국어 질문"
