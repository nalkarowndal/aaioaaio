"""Run: streamlit run scripts/markdown_fixture.py (for real browser QA)."""
from pathlib import Path
import streamlit as st
from core.markdown_render import render_assistant_markdown

st.set_page_config(page_title='Markdown QA', layout='wide')
css=(Path(__file__).resolve().parents[1]/'styles.css').read_text(encoding='utf-8')
st.markdown(f'<style>{css}</style>',unsafe_allow_html=True)
st.title('Markdown 렌더링 테스트')
with st.chat_message('assistant'):
    render_assistant_markdown('''# 제목 H1
## 제목 H2
### 제목 H3
**굵게** 및 [링크](https://example.com)

- 목록 1
  - 중첩 목록

> 인용문

```python
print("codeblock")
```

| 매우 긴 첫 번째 열의 이름과 값 | 두 번째 열 | 세 번째 열 | 네 번째 열 | 다섯 번째 열 |
| --- | --- | --- | --- | --- |
| long-single-line-column-value-to-test-horizontal-scroll | A | B | C | D |

스크립트 입력(실행되지 않아야 함): `<script>alert('x')</script>`''')