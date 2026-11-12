"""AI Studio: a Streamlit/Groq chat workspace with safe Markdown and attachments."""
from __future__ import annotations

import base64
import os
from pathlib import Path

import streamlit as st
from openai import OpenAI, APITimeoutError, APIConnectionError, AuthenticationError, RateLimitError

from core.attachments import ALLOWED_TYPES, MAX_UPLOADS, prepare_image, remove_attachment, upload_snapshot
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
    ('uploader_generation', 0), ('last_error', ''),
):
    if key not in st.session_state:
        st.session_state[key] = default

key = api_key()
with st.sidebar:
    st.subheader('환경 설정')
    st.caption('브라우저에서 비밀키를 직접 입력하거나 표시하지 않습니다.')
    st.write('Groq API: ' + ('키 설정됨 · 연결 미검증' if key else '키 미설정'))
    model = st.text_input('텍스트 모델', value=MODEL_DEFAULT, help='Groq에서 지원하는 모델 ID')
    vision_model = st.text_input('이미지 모델 (선택)', value=os.getenv('GROQ_VISION_MODEL', ''),
                                 help='Groq에서 이미지 입력을 지원하는 모델 ID')
    temperature = st.slider('Temperature', 0.0, 1.5, 0.6, 0.1)
    max_tokens = st.slider('최대 응답 토큰', 256, 4096, 1024, 256)
    if st.button('대화 초기화', use_container_width=True):
        st.session_state.chat_history = []
        st.session_state.last_error = ''
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

with st.expander('첨부파일 관리', expanded=False):
    uploads = st.file_uploader(
        '문서 또는 이미지 첨부 (한 번에 여러 개 선택 가능)',
        type=sorted(ext.lstrip('.') for ext in ALLOWED_TYPES),
        accept_multiple_files=True,
        key=f'files_{st.session_state.uploader_generation}',
        max_upload_size=10,
        help='개별 최대 10MB, 최대 8개까지 추가됩니다.',
    )
    if uploads:
        samples = [(file.name, file.getvalue()) for file in uploads]
        st.session_state.attachments, st.session_state.blocked_files = upload_snapshot(
            st.session_state.attachments, st.session_state.blocked_files, samples
        )
        if len(uploads) > MAX_UPLOADS:
            st.warning('한 번에 최대 8개까지만 보관됩니다.')

    st.caption(f'선택된 파일: {len(st.session_state.attachments)}/{MAX_UPLOADS}')
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
    if st.button('첨부 선택 초기화', help='모든 첨부 항목과 업로더 선택을 초기화'):
        st.session_state.attachments = {}
        st.session_state.blocked_files = set()
        st.session_state.uploader_generation += 1
        st.rerun()

if st.session_state.last_error:
    st.warning(st.session_state.last_error)

for msg in st.session_state.chat_history:
    with st.chat_message(msg['role'], avatar=':material/auto_awesome:' if msg['role'] == 'assistant' else None):
        render_assistant_markdown(msg['content'])

message = st.chat_input('질문을 입력하세요 · 첨부파일은 위의 첨부파일 관리에서 선택하세요')
if message and message.strip():
    user_text = message.strip()
    attached = [f"{item['name']} ({'준비됨' if item['status'] == 'ready' else '읽기 실패'})" for item in st.session_state.attachments.values()]
    display_text = user_text + ('\n\n첨부: ' + ', '.join(attached) if attached else '')
    history = st.session_state.chat_history
    history.append({'role': 'user', 'content': display_text})
    st.session_state.last_error = ''

    if not key:
        st.session_state.last_error = 'Groq API 키가 설정되지 않았습니다. 환경변수 GROQ_API_KEY를 설정해 주세요. AI 응답은 생성되지 않았습니다.'
    else:
        messages = [{'role': 'system', 'content': 'You are a careful, accurate AI assistant. Answer in Korean unless asked otherwise. Use Markdown.'}]
        for previous in history[-13:-1]:
            if previous['role'] in ('user', 'assistant'):
                messages.append({'role': previous['role'], 'content': previous['content']})

        blocks = []
        image_count = 0
        for item in st.session_state.attachments.values():
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
            st.session_state.last_error = '이미지가 선택되었습니다. 환경 설정에 이미지 입력을 지원하는 Groq 모델 ID를 지정해 주세요.'
        elif not target_model:
            st.session_state.last_error = '설정된 모델 ID가 없습니다.'
        else:
            if image_count:
                parts = [{'type': 'text', 'text': question}]
                for item in st.session_state.attachments.values():
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
                    with st.spinner('AI 응답 생성 중...'):
                        answer = OpenAI(base_url='https://api.groq.com/openai/v1', api_key=key,
                                        timeout=40.0, max_retries=1).chat.completions.create(
                            model=target_model, messages=messages,
                            temperature=temperature, max_tokens=max_tokens
                        )
                    reply = (answer.choices[0].message.content or '').strip()
                    if reply:
                        history.append({'role': 'assistant', 'content': reply})
                    else:
                        st.session_state.last_error = '모델 응답이 비어 있어 표시할 내용이 없습니다.'
                except AuthenticationError:
                    st.session_state.last_error = 'Groq 인증에 실패했습니다. 키 설정을 확인해 주세요.'
                except RateLimitError:
                    st.session_state.last_error = '요청 한도를 초과했습니다. 잠시 후 다시 시도해 주세요.'
                except (APITimeoutError, APIConnectionError):
                    st.session_state.last_error = 'Groq 서버 연결 또는 응답 시간이 초과되었습니다.'
                except Exception:
                    st.session_state.last_error = 'AI 요청 중 오류가 발생했습니다. 모델 및 API 상태를 확인해 주세요.'
    st.rerun()