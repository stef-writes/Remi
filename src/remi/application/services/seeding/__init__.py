"""Portfolio loading — batch report ingestion from report exports.

``PortfolioLoader`` ingests a directory of AppFolio reports in two passes
(property_directory first, everything else second), then runs a single
embedding pass and returns a ``LoadResult`` summary.
"""

from remi.application.services.seeding.service import (
    LoadResult,
    PortfolioLoader,
    discover_reports,
)

__all__ = ["LoadResult", "PortfolioLoader", "discover_reports"]
