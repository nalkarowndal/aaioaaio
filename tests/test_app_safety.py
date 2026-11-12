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
    assert 'accept_multiple_files=True' in source
    assert 'remove_attachment(' in source


def test_no_secrets_access_at_import_time():
    source=APP.read_text(encoding='utf-8')
    assert 'st.secrets["GROQ_API_KEY"]' not in source
    assert 'GROQ_API_KEY = st.secrets' not in source


def test_mobile_css_and_markdown_overflow():
    css=CSS.read_text(encoding='utf-8')
    assert '@media (max-width:420px)' in css
    assert 'overflow-x:auto' in css
    assert '[data-testid="stChatMessage"]' in css