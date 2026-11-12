"""Deterministic file identity, bounded parsing, and safe VLM image preparation."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
from pathlib import Path
from typing import Iterable

IMAGE_TYPES = {'.png', '.jpg', '.jpeg', '.webp'}
TEXT_TYPES = {'.txt', '.md', '.py', '.js', '.ts', '.json', '.yml', '.yaml'}
DOCUMENT_TYPES = TEXT_TYPES | {'.pdf', '.docx'}
ALLOWED_TYPES = IMAGE_TYPES | DOCUMENT_TYPES
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_UPLOADS = 8


@dataclass(frozen=True)
class ParsedDocument:
    text: str
    truncated: bool
    status: str = 'ready'


def fingerprint(filename: str, data: bytes) -> str:
    """Content-addressed key; distinguish same filenames with different bytes."""
    h = hashlib.sha256()
    h.update(filename.encode('utf-8', errors='replace'))
    h.update(b'\0')
    h.update(data)
    return h.hexdigest()


def _is_safe_size(raw: bytes) -> None:
    if len(raw) > MAX_FILE_BYTES:
        raise ValueError('파일 용량은 10MB 이하여야 합니다.')
    if not raw:
        raise ValueError('빈 파일은 첨부할 수 없습니다.')


def parse_document(filename: str, raw: bytes, *, max_chars: int = 12000) -> ParsedDocument:
    """Extract bounded text, preserving DOCX document order and truncation status."""
    ext = Path(filename).suffix.lower()
    if ext not in DOCUMENT_TYPES:
        raise ValueError('지원하지 않는 문서 형식입니다.')
    _is_safe_size(raw)
    if max_chars < 1:
        raise ValueError('max_chars must be positive')

    if ext in TEXT_TYPES:
        try:
            text = raw.decode('utf-8-sig')
        except UnicodeDecodeError as exc:
            raise ValueError('UTF-8로 읽을 수 없는 텍스트 파일입니다.') from exc
    elif ext == '.pdf':
        from pypdf import PdfReader
        try:
            doc = PdfReader(io.BytesIO(raw))
            text = '\n\n'.join(page.extract_text() or '' for page in doc.pages)
        except Exception as exc:
            raise ValueError('PDF 텍스트 추출에 실패했습니다.') from exc
    else:
        from docx import Document
        from docx.oxml.ns import qn
        try:
            document = Document(io.BytesIO(raw))
            lines = []
            for el in document.element.body.iterchildren():
                if el.tag == qn('w:p'):
                    paragraph = ''.join(node.text or '' for node in el.iter(qn('w:t')))
                    if paragraph.strip():
                        lines.append(paragraph)
                elif el.tag == qn('w:tbl'):
                    for row in el.iter(qn('w:tr')):
                        cells=[]
                        for cell in row.iterchildren(qn('w:tc')):
                            cells.append(' '.join(node.text or '' for node in cell.iter(qn('w:t'))))
                        lines.append(' | '.join(cells))
            text = '\n'.join(lines)
        except Exception as exc:
            raise ValueError('DOCX 텍스트 추출에 실패했습니다.') from exc
    text = text.strip()
    return ParsedDocument(text=text[:max_chars], truncated=len(text)>max_chars)


def prepare_image(raw: bytes, *, max_pixels: int = 18_000_000) -> tuple[str, bytes]:
    """Normalize RGBA/transparent images to bounded JPEG without exposing errors."""
    from PIL import Image, ImageOps, UnidentifiedImageError
    _is_safe_size(raw)
    try:
        with Image.open(io.BytesIO(raw)) as im:
            if im.width * im.height > max_pixels:
                raise ValueError('이미지 해상도가 허용 범위를 초과합니다.')
            im = ImageOps.exif_transpose(im)
            if im.mode in ('RGBA', 'LA', 'P'):
                rgba=im.convert('RGBA')
                canvas=Image.new('RGB', rgba.size, (255,255,255))
                canvas.paste(rgba, mask=rgba.getchannel('A'))
                image=canvas
            else:
                image=im.convert('RGB')
            target=io.BytesIO()
            image.save(target, format='JPEG', quality=86, optimize=True)
            return 'image/jpeg', target.getvalue()
    except ValueError:
        raise
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError) as exc:
        raise ValueError('이미지를 안전하게 읽을 수 없습니다.') from exc


def upload_snapshot(current: dict, blocked: set, files: Iterable[tuple[str,bytes]]) -> tuple[dict,set]:
    """Reconcile uploader snapshots without re-inserting individually removed items."""
    result = dict(current)
    for name, raw in files:
        digest=fingerprint(name, raw)
        if digest in blocked or digest in result or len(result)>=MAX_UPLOADS:
            continue
        ext=Path(name).suffix.lower()
        if ext not in ALLOWED_TYPES:
            continue
        try:
            if ext in IMAGE_TYPES:
                prepare_image(raw)
                item={'name':name,'kind':'image','bytes':raw,'status':'ready','content':'','truncated':False}
            else:
                document=parse_document(name,raw)
                item={'name':name,'kind':'document','bytes':raw,'content':document.text,'status':document.status,'truncated':document.truncated}
        except ValueError:
            item={'name':name,'kind':'image' if ext in IMAGE_TYPES else 'document','bytes':b'','content':'','status':'error','truncated':False}
        result[digest]=item
    return result, blocked


def remove_attachment(current: dict, blocked: set, attachment_id: str) -> tuple[dict,set]:
    out=dict(current)
    out.pop(attachment_id,None)
    return out, set(blocked)|{attachment_id}