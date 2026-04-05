"""Document content management — types, stores, parsers.

Public API::

    from remi.agent.documents import DocumentContent, ContentStore, parse_document
"""

from remi.agent.documents.parsers import parse_document
from remi.agent.documents.types import (
    ContentStore,
    DocumentContent,
    DocumentKind,
    TextChunk,
)

__all__ = [
    "ContentStore",
    "DocumentContent",
    "DocumentKind",
    "TextChunk",
    "parse_document",
]
