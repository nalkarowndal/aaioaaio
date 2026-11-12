"""AI Studio: a Streamlit/Groq chat workspace with safe Markdown and attachments."""
from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path
import sqlite3

import streamlit as st
from openai import OpenAI, APITimeoutError, APIConnectionError, AuthenticationError, RateLimitError

from core.attachments import ALLOWED_TYPES, MAX_UPLOADS, prepare_image, remove_attachment, upload_snapshot
from core.conversations import ConversationStore
from core.chat_ops import editable_question_text, edit_user_message, regenerate_source, stream_text_chunks
from core.markdown_render import render_assistant_markdown

st.set_page_config(page_title='AI Studio', page_icon='✨', layout='wide', initial_sidebar_state='collapsed')

APP_DIR = Path(__file__).resolve().parent
MODEL_DEFAULT = 'openai/gpt-oss-120b'
css = (APP_DIR / 'styles.css').read_text(encoding='utf-8')
st.markdown(f'<style>{css}</style>', unsafe_allow_html=True)  # Static local stylesheet only.


def api_key() -> str:
    """Allow env and Streamlit secrets without requiring a secrets file."""
    env_key = os.environ.get('GROQ_API_KEY', '').strip()
    if env_key:
        return env_key
    try:
        return str(st.secrets.get('GROQ_API_KEY', '')).strip()
    except (FileNotFoundError, KeyError, AttributeError):
        return ''


for key, default in (
    ('chat_history', [
        {'role': 'assistant', 'content': '안녕하세요! **AI Studio**입니다. Markdown, 코드블록, 표와 여러 문서·이미지를 활용해 대화할 수 있습니다.'}
    ]),
    ('attachments', {}), ('blocked_files', set()),
    ('upload_notice', ''), ('last_error', ''),
    ('active_conversation_id', None), ('history_session_owner', None),
    ('history_loaded', False), ('history_notice', ''), ('delete_pending', None),
    ('pending_generate', False), ('pending_regenerate_index', None),
):
    if key not in st.session_state:
        st.session_state[key] = default

def conversation_owner() -> str:
    """OIDC users get isolated histories; guests never share a public history."""
    try:
        if st.user.is_logged_in:
            subject = str(st.user.get('sub', '')).strip()
            issuer = str(st.user.get('iss', 'oidc')).strip()
            if subject:
                digest = hashlib.sha256((issuer + ':' + subject).encode('utf-8')).hexdigest()
                return 'oidc:' + digest
    except (AttributeError, KeyError, RuntimeError):
        pass
    # Unauthenticated persistence is permitted only on explicitly trusted
    # single-user local installations; NEVER set this on a public deployment.
    if os.getenv('AI_STUDIO_SINGLE_USER_HISTORY', '') == '1':
        return 'local:single-user'
    return ''


def reset_active_chat() -> None:
    st.session_state.active_conversation_id = None
    st.session_state.chat_history = []
    st.session_state.attachments = {}
    st.session_state.blocked_files = set()
    st.session_state.upload_notice = ''
    st.session_state.last_error = ''
    st.session_state.delete_pending = None
    st.session_state.pending_generate = False
    st.session_state.pending_regenerate_index = None


history_owner = conversation_owner()
history_store = None
if history_owner:
    try:
        db_path = Path(os.getenv('AI_STUDIO_HISTORY_DB', str(APP_DIR / 'data' / 'conversations.sqlite3')))
        history_store = ConversationStore(db_path)
    except (sqlite3.Error, OSError):
        st.warning('대화 기록 저장소를 열 수 없습니다. 현재 세션에서만 채팅이 유지됩니다.')

# Never carry one user or one conversation's file attachments into another.
if st.session_state.history_session_owner is None:
    # First page load: retain the original greeting until saved data is found.
    st.session_state.history_session_owner = history_owner
elif st.session_state.history_session_owner != history_owner:
    reset_active_chat()
    st.session_state.history_session_owner = history_owner
    st.session_state.history_loaded = False
if history_store and not st.session_state.history_loaded:
    latest = history_store.list(history_owner, limit=1)
    if latest:
        restored = history_store.get(history_owner, latest[0]['id'])
        if restored:
            st.session_state.active_conversation_id = restored['id']
            st.session_state.chat_history = restored['messages']
    st.session_state.history_loaded = True


def persist_chat() -> None:
    """Persist a user message before external calls, then the completed reply."""
    if not history_store:
        return
    try:
        active_id = st.session_state.active_conversation_id
        if active_id is None:
            st.session_state.active_conversation_id = history_store.create(
                history_owner, st.session_state.chat_history)
        elif not history_store.save(history_owner, active_id, st.session_state.chat_history):
            raise ValueError('삭제된 대화에 저장할 수 없습니다.')
        st.session_state.history_notice = ''
    except (sqlite3.Error, OSError, ValueError):
        st.session_state.history_notice = '대화 기록을 저장하지 못했습니다. 현재 세션의 내용은 유지됩니다.'


key = api_key()
with st.sidebar:
    if history_store:
        st.subheader('대화 기록')
        if history_owner == 'local:single-user':
            st.caption('로컬 단일 사용자 저장소 · 공개 서버에서는 사용하지 마세요.')
        if st.button('새 대화', use_container_width=True, key='new_conversation'):
            reset_active_chat()
            st.rerun()
        history_query = st.text_input('대화 검색', placeholder='제목 또는 대화 내용', key='history_search')
        conversations = history_store.list(history_owner, query=history_query)
        if not conversations:
            st.caption('저장된 대화가 없습니다.')
        for item in conversations:
            if st.button(item['title'][:45], key='open_' + item['id'],
                         help=item['title'], use_container_width=True):
                restored = history_store.get(history_owner, item['id'])
                if restored:
                    reset_active_chat()
                    st.session_state.active_conversation_id = restored['id']
                    st.session_state.chat_history = restored['messages']
                    st.rerun()
        active_id = st.session_state.active_conversation_id
        if active_id:
            current = history_store.get(history_owner, active_id)
            if current:
                with st.expander('현재 대화 관리', expanded=False):
                    new_title = st.text_input('대화 이름', value=current['title'],
                                              key='title_' + active_id)
                    if st.button('이름 저장', key='rename_conversation'):
                        try:
                            history_store.rename(history_owner, active_id, new_title)
                            st.rerun()
                        except ValueError:
                            st.warning('비어 있지 않은 이름을 입력하세요.')
                    if st.button('대화 삭제', key='request_delete'):
                        st.session_state.delete_pending = active_id
                    if st.session_state.delete_pending == active_id:
                        st.warning('삭제한 대화는 복구할 수 없습니다.')
                        if st.button('삭제 확인', key='confirm_delete'):
                            history_store.delete(history_owner, active_id)
                            reset_active_chat()
                            st.rerun()
        st.divider()
    else:
        st.caption('대화 기록은 현재 세션에만 유지됩니다. 로컬 개인용 저장은 환경 변수 AI_STUDIO_SINGLE_USER_HISTORY=1 로 활성화하세요.')
    st.subheader('환경 설정')
    st.caption('브라우저에서 비밀키를 직접 입력하거나 표시하지 않습니다.')
    st.write('Groq API: ' + ('키 설정됨 · 연결 미검증' if key else '키 미설정'))
    model = st.text_input('텍스트 모델', value=MODEL_DEFAULT, help='Groq에서 지원하는 모델 ID')
    vision_model = st.text_input('이미지 모델 (선택)', value=os.getenv('GROQ_VISION_MODEL', ''),
                                 help='Groq에서 이미지 입력을 지원하는 모델 ID')
    temperature = st.slider('Temperature', 0.0, 1.5, 0.6, 0.1)
    max_tokens = st.slider('최대 응답 토큰', 256, 4096, 1024, 256)
    if not history_store and st.button('대화 초기화', use_container_width=True):
        reset_active_chat()
        st.rerun()

# Static HTML shell. Untrusted message or filename text is never inserted here.
st.markdown('''
<header class="glass-header" aria-label="AI Studio">
  <div class="header-left">
    <div class="brand-icon-wrapper" aria-hidden="true">✦</div>
    <div class="brand-text">
      <h1 class="brand-title">AI Studio</h1>
      <span class="brand-subtitle">AI High-Speed Multimodal Engine</span>
    </div>
  </div>
  <div class="header-right"><span class="glass-badge">AI Workspace</span></div>
</header>
''', unsafe_allow_html=True)

if st.session_state.history_notice:
    st.warning(st.session_state.history_notice)
if st.session_state.last_error:
    st.warning(st.session_state.last_error)

for message_index, msg in enumerate(st.session_state.chat_history):
    with st.chat_message(msg['role'], avatar=':material/auto_awesome:' if msg['role'] == 'assistant' else None):
        render_assistant_markdown(msg['content'])
        # One compact per-message action menu; no permanent rows of controls.
        is_answer = (msg['role'] == 'assistant' and message_index > 0
                     and st.session_state.chat_history[message_index - 1]['role'] == 'user')
        if msg['role'] == 'user' or is_answer:
            with st.popover('작업', icon=':material/more_horiz:'):
                st.caption('복사: 아래 원문 오른쪽 위의 복사 아이콘을 사용하세요.')
                st.code(msg['content'], language=None)
                if msg['role'] == 'user':
                    with st.form('edit_form_' + str(message_index)):
                        edit_text = st.text_area(
                            '질문 수정', value=editable_question_text(msg['content']),
                            max_chars=12_000,
                            key=('edit_' + str(st.session_state.active_conversation_id)
                                 + '_' + str(message_index) + '_'
                                 + hashlib.sha256(msg['content'].encode('utf-8')).hexdigest()[:12]),
                        )
                        st.caption('수정하면 이 질문 이후 대화가 제거됩니다. 첨부파일은 다시 선택해야 합니다.')
                        if st.form_submit_button('수정 후 다시 질문'):
                            try:
                                updated = edit_user_message(
                                    st.session_state.chat_history, message_index, edit_text)
                                st.session_state.chat_history = updated
                                st.session_state.attachments = {}
                                st.session_state.blocked_files = set()
                                st.session_state.pending_regenerate_index = None
                                st.session_state.pending_generate = True
                                persist_chat()
                                st.rerun()
                            except ValueError as error:
                                st.warning(str(error))
                elif st.button('답변 다시 생성', key='regen_' + str(message_index)):
                    try:
                        regenerate_source(st.session_state.chat_history, message_index)
                    except ValueError as error:
                        st.session_state.last_error = str(error)
                    else:
                        st.session_state.pending_regenerate_index = message_index
                    st.rerun()
                if is_answer:
                    st.caption('이전 답변을 재생성하면 이후 대화는 성공 시에만 대체됩니다.')

# Keep attachment controls out of the way until files are actually present.
# Previously attached files stay available for subsequent prompts until removed.
if st.session_state.attachments:
    with st.expander(f"첨부파일 {len(st.session_state.attachments)}/{MAX_UPLOADS} · 관리", expanded=False):
        st.caption('입력창의 첨부 버튼으로 파일을 추가하세요. 개별 파일 10MB, 최대 8개까지 보관합니다.')
        for attachment_id, item in list(st.session_state.attachments.items()):
            left, right = st.columns([5, 1], vertical_alignment='center')
            with left:
                symbol = '이미지' if item['kind'] == 'image' else '문서'
                status = {'ready': '준비됨', 'error': '읽기 실패'}.get(item['status'], '확인 필요')
                extra = ' · 일부 텍스트만 추출' if item['truncated'] else ''
                st.text(item['name'])
                st.caption(f'{symbol} · {status}{extra}')
            with right:
                if st.button('제거', key=f'rm_{attachment_id}', help=f"{item['name']} 제거"):
                    st.session_state.attachments, st.session_state.blocked_files = remove_attachment(
                        st.session_state.attachments, st.session_state.blocked_files, attachment_id
                    )
                    st.rerun()
            if item['kind'] == 'image' and item['status'] == 'ready':
                with st.expander(f"이미지 미리보기: {item['name']}"):
                    st.image(item['bytes'], use_container_width=True)
        if st.button('모든 첨부 제거', help='보관된 첨부 항목 모두 삭제'):
            st.session_state.attachments = {}
            st.session_state.blocked_files = set()
            st.session_state.upload_notice = ''
            st.rerun()

if st.session_state.upload_notice:
    st.info(st.session_state.upload_notice)

# The native chat composer owns the attachment entry point, instead of
# displaying a second file-upload widget above the conversation.
submission = st.chat_input(
    '질문을 입력하거나 파일을 첨부하세요',
    accept_file='multiple',
    file_type=sorted(ext.lstrip('.') for ext in ALLOWED_TYPES),
    max_upload_size=10,
    key='unified_chat_composer',
)
message = ''
if submission is not None:
    message = (submission.text or '').strip()
    submitted_files = [(file.name, file.getvalue()) for file in submission.files]
    if submitted_files:
        # Each composer submission is a deliberate new attachment action.
        # Blocked IDs only protect the old uploader snapshot, not re-selection.
        st.session_state.blocked_files = set()
        before_count = len(st.session_state.attachments)
        st.session_state.attachments, st.session_state.blocked_files = upload_snapshot(
            st.session_state.attachments, st.session_state.blocked_files, submitted_files
        )
        accepted = len(st.session_state.attachments) - before_count
        if accepted < len(submitted_files):
            st.session_state.upload_notice = '일부 파일을 추가하지 못했습니다. 최대 8개·파일당 10MB 및 중복 여부를 확인하세요.'
        else:
            st.session_state.upload_notice = ''
    # A file-only submission stages the attachments without calling Groq.
    if not message:
        st.rerun()

# Keep regeneration atomic: retain the existing reply if the request fails.
pending_regenerate = st.session_state.pending_regenerate_index
pending_generate = st.session_state.pending_generate
if message or pending_generate or pending_regenerate is not None:
    history = st.session_state.chat_history
    st.session_state.pending_generate = False
    st.session_state.pending_regenerate_index = None
    replacing_index = None
    attachments_for_request = []

    if message:
        user_text = message.strip()
        attachments_for_request = list(st.session_state.attachments.values())
        attached = [
            f"{item['name']} ({'준비됨' if item['status'] == 'ready' else '읽기 실패'})"
            for item in attachments_for_request
        ]
        display_text = user_text + ('\n\n첨부: ' + ', '.join(attached) if attached else '')
        history.append({'role': 'user', 'content': display_text})
        persist_chat()  # A sent question is never lost if streaming subsequently fails.
        history_before = history[:-1]
    elif pending_generate:
        if not history or history[-1]['role'] != 'user':
            st.session_state.last_error = '수정한 질문을 찾을 수 없습니다.'
            st.rerun()
        user_text = history[-1]['content']
        history_before = history[:-1]
        # Earlier file bytes are never silently reused after editing.
    else:
        try:
            history_including_user, user_text = regenerate_source(history, pending_regenerate)
            history_before = history_including_user[:-1]
            replacing_index = pending_regenerate
        except ValueError as error:
            st.session_state.last_error = str(error)
            st.rerun()

    st.session_state.last_error = ''
    if not key:
        st.session_state.last_error = (
            'Groq API 키가 설정되지 않았습니다. 환경변수 GROQ_API_KEY를 설정해 주세요. '
            'AI 응답은 생성되지 않았습니다.'
        )
    else:
        messages = [{
            'role': 'system',
            'content': 'You are a careful, accurate AI assistant. Answer in Korean unless asked otherwise. Use Markdown.'
        }]
        for previous in history_before[-12:]:
            if previous['role'] in ('user', 'assistant'):
                messages.append({'role': previous['role'], 'content': previous['content']})

        blocks = []
        image_count = 0
        for item in attachments_for_request:
            if item['status'] != 'ready':
                continue
            if item['kind'] == 'document':
                note = '\n[주의: 문서 일부만 추출됨]' if item['truncated'] else ''
                blocks.append(f"[참고 문서: {item['name']}{note}]\n{item['content']}\n[/참고 문서]")
            else:
                image_count += 1

        question = user_text
        if blocks:
            question = '\n\n'.join(blocks) + '\n\n[사용자 질문]\n' + user_text
        target_model = vision_model.strip() if image_count else model.strip()

        if image_count and not target_model:
            st.session_state.last_error = (
                '이미지가 선택되었습니다. 환경 설정에 이미지 입력을 지원하는 Groq 모델 ID를 지정해 주세요.'
            )
        elif not target_model:
            st.session_state.last_error = '설정된 모델 ID가 없습니다.'
        else:
            if image_count:
                parts = [{'type': 'text', 'text': question}]
                for item in attachments_for_request:
                    if item['status'] == 'ready' and item['kind'] == 'image':
                        try:
                            mime, encoded_bytes = prepare_image(item['bytes'])
                            url = 'data:' + mime + ';base64,' + base64.b64encode(encoded_bytes).decode('ascii')
                            parts.append({'type': 'image_url', 'image_url': {'url': url}})
                        except ValueError:
                            st.session_state.last_error = '일부 이미지를 안전하게 읽을 수 없습니다.'
                messages.append({'role': 'user', 'content': parts})
            else:
                messages.append({'role': 'user', 'content': question})

            if not st.session_state.last_error:
                try:
                    # The stream is consumed inside the API client's lifetime.
                    # No partially received response is persisted.
                    with OpenAI(base_url='https://api.groq.com/openai/v1',
                                api_key=key, timeout=40.0, max_retries=1) as client:
                        with st.chat_message('assistant', avatar=':material/auto_awesome:'):
                            with st.spinner('AI 답변 생성 중...'):
                                stream = client.chat.completions.create(
                                    model=target_model, messages=messages, stream=True,
                                    temperature=temperature, max_tokens=max_tokens
                                )
                                reply = st.write_stream(stream_text_chunks(stream))
                    if isinstance(reply, str) and reply.strip():
                        new_answer = {'role': 'assistant', 'content': reply.strip()}
                        if replacing_index is None:
                            history.append(new_answer)
                        else:
                            # Any later turns become inconsistent with the new answer.
                            st.session_state.chat_history = history[:replacing_index] + [new_answer]
                        persist_chat()
                    else:
                        st.session_state.last_error = '모델 응답이 비어 있어 표시할 내용이 없습니다.'
                except AuthenticationError:
                    st.session_state.last_error = 'Groq 인증에 실패했습니다. 키 설정을 확인해 주세요.'
                except RateLimitError:
                    st.session_state.last_error = '요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.'
                except (APITimeoutError, APIConnectionError):
                    st.session_state.last_error = 'Groq 서버 연결 또는 응답 시간이 초과되었습니다.'
                except ValueError:
                    st.session_state.last_error = '답변 길이가 저장 가능한 한도를 초과했습니다.'
                except Exception:
                    st.session_state.last_error = 'AI 요청 중 오류가 발생했습니다. 모델 및 API 상태를 확인해 주세요.'
    st.rerun()