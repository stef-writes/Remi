"""knowledge.ingestion — structured entity extraction from documents.

Submodules:
  base            — IngestionResult (shared result type)
  service         — IngestionService (orchestrator)
  rent_roll       — AppFolio Rent Roll parser
  delinquency     — AppFolio Delinquency parser
  lease_expiration — AppFolio Lease Expiration parser
  generic         — heuristic column-based fallback for unknown doc types
  helpers         — parse_address, occupancy_to_unit_status, entity_id_from_row
"""

from remi.knowledge.ingestion.base import IngestionResult
from remi.knowledge.ingestion.service import IngestionService

__all__ = ["IngestionResult", "IngestionService"]
