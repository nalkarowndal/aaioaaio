"""P7 deterministic chat actions and streaming safety."""
from types import SimpleNamespace

import pytest

from core.chat_ops import editable_question_text, edit_user_message, regenerate_source, stream_text_chunks


def _chunk(text=None, *, with_choice=True):
    if not with_choice:
        return SimpleNamespace(choices=[])
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


def sample_history():
    return [
        {'role': 'assistant', 'content': '환영'},
        {'role': 'user', 'content': '첫 질문'},
        {'role': 'assistant', 'content': '첫 답변'},
        {'role': 'user', 'content': '두 번째 질문'},
        {'role': 'assistant', 'content': '두 번째 답변'},
    ]


def test_edit_old_turn_discards_all_following_messages():
    old = sample_history()
    updated = edit_user_message(old, 1, ' 수정 질문 ')
    assert updated == [
        {'role': 'assistant', 'content': '환영'},
        {'role': 'user', 'content': '수정 질문'},
    ]
    assert old[1]['content'] == '첫 질문'
    assert len(old) == 5


def test_edit_last_question_and_validate_input():
    old = sample_history()
    assert edit_user_message(old, 3, '새 질문')[-1]['content'] == '새 질문'
    for index, text in ((1, ''), (1, ' '), (1, 'x' * 12001), (2, '무효')):
        with pytest.raises(ValueError):
            edit_user_message(old, index, text)
    with pytest.raises(ValueError):
        edit_user_message(old, 99, '무효')


def test_regeneration_includes_only_prerequisite_turns():
    history = sample_history()
    context, question = regenerate_source(history, 2)
    assert question == '첫 질문'
    assert context == history[:2]
    context2, question2 = regenerate_source(history, 4)
    assert question2 == '두 번째 질문'
    assert context2 == history[:4]
    assert len(history) == 5


def test_regeneration_refuses_welcome_and_user_messages():
    history = sample_history()
    for index in (0, 1, 3, 9):
        with pytest.raises(ValueError):
            regenerate_source(history, index)


def test_regeneration_refuses_filename_only_attachment_history():
    history = [
        {'role': 'user', 'content': '사진 내용은?\n\n첨부: puppy.png (준비됨)'},
        {'role': 'assistant', 'content': '사진이 있습니다.'},
    ]
    with pytest.raises(ValueError, match='원본 파일'):
        regenerate_source(history, 1)


def test_stream_text_chunks_ignores_empty_delta_and_returns_joinable_text():
    chunks = [
        _chunk(None), _chunk('', with_choice=True), _chunk(with_choice=False),
        _chunk('안녕'), _chunk('하세요'),
    ]
    assert ''.join(stream_text_chunks(chunks)) == '안녕하세요'


def test_stream_does_not_suppress_midstream_network_errors():
    def broken():
        yield _chunk('일부 내용')
        raise ConnectionError('network down')

    partial = []
    with pytest.raises(ConnectionError):
        for token in stream_text_chunks(broken()):
            partial.append(token)
    assert partial == ['일부 내용']


def test_stream_enforces_max_response_chars():
    with pytest.raises(ValueError, match='답변 길이'):
        list(stream_text_chunks([_chunk('abcd'), _chunk('ef')], max_chars=5))


def test_stream_ignores_non_text_metadata():
    chunks = [_chunk(123), _chunk(None), _chunk('최종')]
    assert ''.join(stream_text_chunks(chunks)) == '최종'



def test_question_editor_excludes_stale_attachment_display_suffix():
    shown = "사진을 설명해 주세요\n\n첨부: old_photo.png (준비됨)"
    assert editable_question_text(shown) == "사진을 설명해 주세요"
    assert editable_question_text("일반 질문") == "일반 질문"
    assert editable_question_text(123) == ""
