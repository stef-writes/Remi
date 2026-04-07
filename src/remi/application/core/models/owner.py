"""Owner — the legal entity that owns a property asset."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from remi.application.core.models._helpers import _utcnow
from remi.application.core.models.address import Address
from remi.application.core.models.enums import OwnerType


class Owner(BaseModel, frozen=True):
    """The legal entity that owns a property asset.

    May be an individual investor, an LLC, a trust, a partnership, or a
    corporation.  Owners are associated with properties (not units) and are
    active participants in operational decisions — approving payment plans,
    authorizing non-renewals, funding capital improvements.
    """

    id: str
    name: str
    owner_type: OwnerType = OwnerType.OTHER
    company: str | None = None
    email: str = ""
    phone: str | None = None
    address: Address | None = None
    content_hash: str | None = None
    source_document_id: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
