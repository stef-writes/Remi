"""REST endpoints for portfolios."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from remi.api.dependencies import get_portfolio_query, get_property_store
from remi.api.portfolios.schemas import (
    PortfolioDetail,
    PortfolioListItem,
    PortfolioListResponse,
    PortfolioSummary,
    PropertyInPortfolio,
)
from remi.models.properties import PropertyStore
from remi.services.portfolio_queries import PortfolioQueryService

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


@router.get("", response_model=PortfolioListResponse)
async def list_portfolios(
    manager_id: str | None = None,
    svc: PortfolioQueryService = Depends(get_portfolio_query),
) -> PortfolioListResponse:
    items = await svc.list_portfolios(manager_id=manager_id)
    return PortfolioListResponse(
        portfolios=[PortfolioListItem(**item.model_dump()) for item in items]
    )


@router.get("/{portfolio_id}", response_model=PortfolioDetail)
async def get_portfolio(
    portfolio_id: str,
    ps: PropertyStore = Depends(get_property_store),
) -> PortfolioDetail:
    portfolio = await ps.get_portfolio(portfolio_id)
    if not portfolio:
        raise HTTPException(404, f"Portfolio '{portfolio_id}' not found")
    return PortfolioDetail(
        id=portfolio.id,
        manager_id=portfolio.manager_id,
        name=portfolio.name,
        description=portfolio.description,
        property_ids=portfolio.property_ids,
        created_at=portfolio.created_at.isoformat(),
    )


@router.get("/{portfolio_id}/summary", response_model=PortfolioSummary)
async def portfolio_summary(
    portfolio_id: str,
    svc: PortfolioQueryService = Depends(get_portfolio_query),
) -> PortfolioSummary:
    result = await svc.portfolio_summary(portfolio_id)
    if not result:
        raise HTTPException(404, f"Portfolio '{portfolio_id}' not found")
    return PortfolioSummary(
        portfolio_id=result.portfolio_id,
        name=result.name,
        manager=result.manager,
        total_properties=result.total_properties,
        total_units=result.total_units,
        occupied_units=result.occupied_units,
        occupancy_rate=result.occupancy_rate,
        monthly_revenue=result.monthly_revenue,
        properties=[PropertyInPortfolio(**p.model_dump()) for p in result.properties],
    )
