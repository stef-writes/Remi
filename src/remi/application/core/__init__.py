"""Domain — pure business logic with no infrastructure dependencies.

Public API::

    from remi.application.core import PropertyStore
    from remi.application.core import ChangeSet, EventStore, ...
    from remi.application.core import KnowledgeWriter, ...
"""

from remi.application.core.events import (
    ChangeEvent,
    ChangeSet,
    ChangeSource,
    ChangeType,
    EventStore,
    FieldChange,
)
from remi.application.core.protocols import (
    DocumentRepository,
    EmbedRequest,
    KBEntity,
    KBRelationship,
    KnowledgeReader,
    KnowledgeWriter,
    PropertyStore,
    TextIndexer,
    TextSearchHit,
    VectorSearch,
)

__all__ = [
    "ChangeEvent",
    "ChangeSet",
    "ChangeSource",
    "ChangeType",
    "DocumentRepository",
    "EmbedRequest",
    "EventStore",
    "FieldChange",
    "KBEntity",
    "KBRelationship",
    "KnowledgeReader",
    "KnowledgeWriter",
    "PropertyStore",
    "TextIndexer",
    "TextSearchHit",
    "VectorSearch",
]
