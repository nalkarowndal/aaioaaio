from pathlib import Path

APP=Path(__file__).resolve().parents[1] / 'app.py'
CSS=Path(__file__).resolve().parents[1] / 'styles.css'


def test_ai_response_uses_safe_markdown_renderer():
    source=APP.read_text(encoding='utf-8')
    assert "render_assistant_markdown(msg['content'])" in source
    assert 'content | safe' not in source
    assert '.replace("\\n", "<br>")' not in source


def test_no_forced_page_scroll_script():
    source=APP.read_text(encoding='utf-8')
    assert 'window.parent' not in source
    assert 'trigger_auto_scroll' not in source


def test_multi_file_support_and_individual_removal():
    source=APP.read_text(encoding='utf-8')
    assert "accept_file='multiple'" in source
    assert "max_upload_size=10" in source
    assert "submission.files" in source
    assert 'remove_attachment(' in source
    assert 'st.file_uploader(' not in source


def test_file_only_submission_stages_attachments_without_model_call():
    source=APP.read_text(encoding='utf-8')
    assert 'if not message:\\n        st.rerun()' in repr(source)
    assert "message = (submission.text or '').strip()" in source
    assert 'upload_snapshot(' in source


def test_attachment_controls_are_collapsed_until_files_exist():
    source=APP.read_text(encoding='utf-8')
    assert 'if st.session_state.attachments:' in source
    assert 'with st.expander(f"첨부파일 {len(st.session_state.attachments)}/{MAX_UPLOADS} · 관리", expanded=False):' in source


def test_no_secrets_access_at_import_time():
    source=APP.read_text(encoding='utf-8')
    assert 'st.secrets["GROQ_API_KEY"]' not in source
    assert 'GROQ_API_KEY = st.secrets' not in source


def test_mobile_css_and_markdown_overflow():
    css=CSS.read_text(encoding='utf-8')
    assert '@media (max-width:420px)' in css
    assert 'overflow-x:auto' in css
    assert '[data-testid="stChatMessage"]' in css


def test_production_toolbar_does_not_show_deploy_control():
    config=(APP.parent / '.streamlit' / 'config.toml').read_text(encoding='utf-8')
    assert 'toolbarMode = "minimal"' in config


def test_assistant_avatar_uses_brand_material_icon():
    source=APP.read_text(encoding='utf-8')
    assert ':material/auto_awesome:' in source


def test_user_avatar_preserves_role_selector_and_status_labels():
    source=APP.read_text(encoding='utf-8')
    assert "if msg['role'] == 'assistant' else None" in source
    assert "'준비됨' if item['status'] == 'ready' else '읽기 실패'" in source