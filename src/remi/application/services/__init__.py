"""Services — application-level orchestration over domain + agent ports.

    ingestion/      Document ingestion pipeline (parse → extract → resolve → persist)
    embedding/      Vector indexing pipeline for portfolio entities
    seeding/        Batch report loading (PortfolioLoader)
    search.py       RE-aware hybrid search

Entity resolvers live in ``application/portfolio/``, not here.
"""
