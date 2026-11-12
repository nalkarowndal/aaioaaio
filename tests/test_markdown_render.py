from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core.markdown_render import render_assistant_markdown

class FakeStreamlit:
    def __init__(self): self.calls = []
    def markdown(self, body, **kwargs): self.calls.append((body, kwargs))

@pytest.mark.parametrize('body', [
    '# 제목\n\n## 소제목\n\n**강조**',
    '```python\nprint("hello")\n```',
    '| 항목 | 결과 |\n| --- | --- |\n| A | 정상 |',
    '> 인용문\n\n- 항목 1\n- 항목 2',
    '<script>alert("xss")</script>',
])
def test_preserves_markdown_without_enabling_unsafe_html(body):
    ui=FakeStreamlit()
    render_assistant_markdown(body, ui=ui)
    assert ui.calls == [(body, {'unsafe_allow_html': False})]

def test_rejects_non_text_content():
    with pytest.raises(TypeError):
        render_assistant_markdown(None, ui=FakeStreamlit())

def test_does_not_normalize_long_tables():
    cells = '|'.join(f'field{i}' for i in range(40))
    body = '|'+cells+'|\n|'+'|'.join('---' for _ in range(40))+'|'
    ui=FakeStreamlit()
    render_assistant_markdown(body, ui=ui)
    assert ui.calls[0][0] == body