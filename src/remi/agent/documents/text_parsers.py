"""Text-based document parsers for the knowledge base.

Converts raw file bytes into a ``DocumentContent`` with ``kind=text``.
Supports PDF, DOCX, and plain text.  Images produce ``kind=image``
metadata-only documents.

Public surface:
    parse_pdf(filename, content) -> DocumentContent
    parse_docx(filename, content) -> DocumentContent
    parse_text(filename, content, content_type) -> DocumentContent
    parse_image(filename, content, content_type) -> DocumentContent
    chunk_text(raw_text, max_tokens, overlap) -> list[TextChunk]
"""

from __future__ import annotations

import uuid

from remi.agent.documents.types import DocumentContent, DocumentKind, TextChunk

_APPROX_CHARS_PER_TOKEN = 4
_DEFAULT_MAX_TOKENS = 500
_DEFAULT_OVERLAP_TOKENS = 50


# ---------------------------------------------------------------------------
# Chunker — shared by all text parsers
# ---------------------------------------------------------------------------


def chunk_text(
    raw_text: str,
    *,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
    overlap_tokens: int = _DEFAULT_OVERLAP_TOKENS,
    page_breaks: list[int] | None = None,
) -> list[TextChunk]:
    """Split text into overlapping passages, respecting paragraph boundaries.

    *page_breaks* maps character offset to page number (sorted ascending).
    """
    if not raw_text.strip():
        return []

    max_chars = max_tokens * _APPROX_CHARS_PER_TOKEN
    overlap_chars = overlap_tokens * _APPROX_CHARS_PER_TOKEN

    paragraphs = raw_text.split("\n\n")
    chunks: list[TextChunk] = []
    current: list[str] = []
    current_len = 0
    char_offset = 0

    def _page_at(offset: int) -> int | None:
        if not page_breaks:
            return None
        page = 0
        for brk in page_breaks:
            if offset >= brk:
                page += 1
            else:
                break
        return page

    def _flush() -> None:
        nonlocal current, current_len
        if not current:
            return
        text = "\n\n".join(current).strip()
        if text:
            chunks.append(TextChunk(
                index=len(chunks),
                text=text,
                page=_page_at(char_offset - current_len),
            ))
        current = []
        current_len = 0

    for para in paragraphs:
        para_len = len(para) + 2  # account for the \n\n separator
        if current_len + para_len > max_chars and current:
            _flush()
            # Overlap: re-add last paragraph from previous chunk
            if chunks and overlap_chars > 0:
                last_text = chunks[-1].text
                tail = last_text[-overlap_chars:]
                current = [tail]
                current_len = len(tail)
        current.append(para)
        current_len += para_len
        char_offset += para_len

    _flush()
    return chunks


# ---------------------------------------------------------------------------
# PDF parser
# ---------------------------------------------------------------------------


def parse_pdf(filename: str, content: bytes) -> DocumentContent:
    """Extract text from a PDF using pymupdf."""
    try:
        import pymupdf  # noqa: WPS433
    except ImportError as exc:
        raise ImportError(
            "pymupdf is required for PDF parsing. Install with: uv add pymupdf"
        ) from exc

    doc = pymupdf.open(stream=content, filetype="pdf")
    pages: list[str] = []
    page_breaks: list[int] = []
    offset = 0

    for page in doc:
        text = page.get_text()
        page_breaks.append(offset)
        pages.append(text)
        offset += len(text) + 2  # paragraph separator

    raw_text = "\n\n".join(pages)
    doc.close()

    chunks = chunk_text(raw_text, page_breaks=page_breaks)

    return DocumentContent(
        id=f"doc-{uuid.uuid4().hex[:12]}",
        filename=filename,
        content_type="application/pdf",
        kind=DocumentKind.text,
        raw_text=raw_text,
        chunks=chunks,
        page_count=len(pages),
        size_bytes=len(content),
    )


# ---------------------------------------------------------------------------
# DOCX parser
# ---------------------------------------------------------------------------


def parse_docx(filename: str, content: bytes) -> DocumentContent:
    """Extract text from a Word document using python-docx."""
    try:
        import docx  # noqa: WPS433
    except ImportError as exc:
        raise ImportError(
            "python-docx is required for DOCX parsing. Install with: uv add python-docx"
        ) from exc

    import io

    doc = docx.Document(io.BytesIO(content))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    raw_text = "\n\n".join(paragraphs)
    chunks = chunk_text(raw_text)

    return DocumentContent(
        id=f"doc-{uuid.uuid4().hex[:12]}",
        filename=filename,
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        kind=DocumentKind.text,
        raw_text=raw_text,
        chunks=chunks,
        page_count=0,
        size_bytes=len(content),
    )


# ---------------------------------------------------------------------------
# Plain text / Markdown parser
# ---------------------------------------------------------------------------


def parse_text(filename: str, content: bytes, content_type: str) -> DocumentContent:
    """Parse a plain text or markdown file."""
    text = content.decode("utf-8-sig", errors="replace")
    chunks = chunk_text(text)

    return DocumentContent(
        id=f"doc-{uuid.uuid4().hex[:12]}",
        filename=filename,
        content_type=content_type,
        kind=DocumentKind.text,
        raw_text=text,
        chunks=chunks,
        size_bytes=len(content),
    )


# ---------------------------------------------------------------------------
# Image (metadata-only)
# ---------------------------------------------------------------------------


def parse_image(filename: str, content: bytes, content_type: str) -> DocumentContent:
    """Create a metadata-only DocumentContent for an image file."""
    return DocumentContent(
        id=f"doc-{uuid.uuid4().hex[:12]}",
        filename=filename,
        content_type=content_type,
        kind=DocumentKind.image,
        size_bytes=len(content),
    )
