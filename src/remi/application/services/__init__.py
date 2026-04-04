"""Services — application-level orchestration over domain + agent ports.

    queries/        Read-side services: portfolio, dashboard, rent roll, managers, auto-assign
    ingestion/      Document ingestion pipeline (parse → extract → resolve → persist)
    embedding/      Vector indexing pipeline for portfolio entities
    monitoring/     Signal evaluators + time-series snapshot service
    search.py       RE-aware hybrid search
    seed.py         Bootstrap from report exports
"""
