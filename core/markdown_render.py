"""P0: Render untrusted assistant Markdown with Streamlit's Markdown engine.

Keep AI-supplied text out of st.html / unsafe_allow_html=True templates.
This module does *not* parse markdown with regexes or assemble HTML.
"""
from typing import Any


def render_assistant_markdown(content: str, *, ui: Any = None) -> None:
    """Render GitHub-flavored Markdown without permitting raw HTML insertion.

    ``ui`` is injectable for deterministic unit tests; defaults to streamlit.
    No UI chrome/layout is generated, so the existing chat layout is retained.
    """
    if not isinstance(content, str):
        raise TypeError("Assistant content must be a string")
    if ui is None:
        import streamlit as st
        ui = st
    ui.markdown(content, unsafe_allow_html=False)