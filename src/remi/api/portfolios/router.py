"""REST endpoints for portfolios."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter, Depends, HTTPException

from remi.api.dependencies import get_container
from remi.api.portfolios.schemas import (
    PortfolioDetail,
    PortfolioListItem,
    PortfolioListResponse,
    PortfolioSummary,
    PropertyInPortfolio,
)

if TYPE_CHECKING:
    from remi.config.container import Container

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


@router.get("", response_model=PortfolioListResponse)
async def list_portfolios(
    manager_id: str | None = None,
    container: Container = Depends(get_container),
) -> PortfolioListResponse:
    items = await container.portfolio_query.list_portfolios(manager_id=manager_id)
    return PortfolioListResponse(
        portfolios=[PortfolioListItem(**item.model_dump()) for item in items]
    )


@router.get("/{portfolio_id}", response_model=PortfolioDetail)
async def get_portfolio(
    portfolio_id: str,
    container: Container = Depends(get_container),
) -> PortfolioDetail:
    portfolio = await container.property_store.get_portfolio(portfolio_id)
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
    container: Container = Depends(get_container),
) -> PortfolioSummary:
    result = await container.portfolio_query.portfolio_summary(portfolio_id)
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
