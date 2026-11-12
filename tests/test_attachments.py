import io
from PIL import Image
import pytest

from core.attachments import (
    fingerprint, parse_document, prepare_image, upload_snapshot, remove_attachment,
)


def test_same_filename_changed_bytes_get_distinct_ids():
    assert fingerprint('same.txt', b'one') != fingerprint('same.txt', b'two')


def test_text_content_preserved_but_length_is_capped():
    result = parse_document('hello.txt', b'abcdefghijkl', max_chars=7)
    assert result.text == 'abcdefg'
    assert result.truncated is True
    assert result.status == 'ready'


def test_invalid_text_encoding_is_safe_error():
    with pytest.raises(ValueError, match='UTF-8'):
        parse_document('bad.txt', b'\xff')


def test_unrecognized_extension_rejected():
    with pytest.raises(ValueError, match='지원하지 않는'):
        parse_document('bad.exe', b'MZ')


def test_docx_preserves_paragraph_table_paragraph_order():
    from docx import Document
    d = Document()
    d.add_paragraph('first')
    t = d.add_table(rows=1, cols=2)
    t.cell(0, 0).text = 'A'
    t.cell(0, 1).text = 'B'
    d.add_paragraph('last')
    raw=io.BytesIO(); d.save(raw)
    result = parse_document('test.docx', raw.getvalue())
    assert result.text.index('first') < result.text.index('A | B') < result.text.index('last')


def test_transparent_webp_is_encoded_as_jpeg_for_vlm():
    im=Image.new('RGBA', (6, 6), (128, 0, 255, 100))
    out=io.BytesIO(); im.save(out,format='WEBP')
    mime, payload = prepare_image(out.getvalue(), max_pixels=1000)
    assert mime=='image/jpeg'
    assert payload[:3] == b'\xff\xd8\xff'


def test_oversized_image_rejected():
    im=Image.new('RGB',(30,30)); out=io.BytesIO(); im.save(out,format='PNG')
    with pytest.raises(ValueError, match='해상도'):
        prepare_image(out.getvalue(), max_pixels=100)


def test_removed_file_does_not_reappear_without_reset():
    first=fingerprint('a.txt',b'a')
    current, blocked=upload_snapshot({},set(),[('a.txt',b'a')])
    assert first in current
    current, blocked=remove_attachment(current,blocked,first)
    current, blocked=upload_snapshot(current,blocked,[('a.txt',b'a')])
    assert first not in current


def test_two_uploaded_files_remain_independent():
    current,blocked=upload_snapshot({},set(),[('a.txt',b'a'),('b.txt',b'b')])
    assert len(current)==2
    first=fingerprint('a.txt',b'a')
    current,blocked=remove_attachment(current,blocked,first)
    assert len(current)==1
    assert fingerprint('b.txt',b'b') in current