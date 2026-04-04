"""REST endpoints for portfolios."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from remi.application.services.queries import PortfolioQueryService, PortfolioSummaryResult
from remi.application.api.schemas import (
    CreatePortfolioRequest,
    CreatePortfolioResponse,
    PortfolioDetail,
    PortfolioListResponse,
    UpdatePortfolioRequest,
)
from remi.application.core.models import Portfolio
from remi.application.core.protocols import PropertyStore
from remi.application.api.dependencies import get_portfolio_query, get_property_store
from remi.types.errors import ConflictError, NotFoundError
from remi.types.text import slugify as _slugify

router = APIRouter(prefix="/portfolios", tags=["portfolios"])


@router.get("", response_model=PortfolioListResponse)
async def list_portfolios(
    manager_id: str | None = None,
    svc: PortfolioQueryService = Depends(get_portfolio_query),
) -> PortfolioListResponse:
    items = await svc.list_portfolios(manager_id=manager_id)
    return PortfolioListResponse(portfolios=items)


@router.post("", response_model=CreatePortfolioResponse, status_code=201)
async def create_portfolio(
    body: CreatePortfolioRequest,
    ps: PropertyStore = Depends(get_property_store),
) -> CreatePortfolioResponse:
    manager = await ps.get_manager(body.manager_id)
    if not manager:
        raise NotFoundError("Manager", body.manager_id)

    portfolio_id = _slugify(f"portfolio:{body.manager_id}:{body.name}")
    existing = await ps.get_portfolio(portfolio_id)
    if existing:
        raise ConflictError(
            f"Portfolio '{body.name}' already exists for this manager (id={portfolio_id})"
        )

    await ps.upsert_portfolio(
        Portfolio(
            id=portfolio_id,
            manager_id=body.manager_id,
            name=body.name,
            description=body.description,
            asset_class=body.asset_class,
            strategy=body.strategy,
            target_occupancy=body.target_occupancy,
            market=body.market,
        )
    )
    return CreatePortfolioResponse(
        portfolio_id=portfolio_id,
        manager_id=body.manager_id,
        name=body.name,
    )


@router.get("/{portfolio_id}", response_model=PortfolioDetail)
async def get_portfolio(
    portfolio_id: str,
    ps: PropertyStore = Depends(get_property_store),
) -> PortfolioDetail:
    portfolio = await ps.get_portfolio(portfolio_id)
    if not portfolio:
        raise NotFoundError("Portfolio", portfolio_id)
    return PortfolioDetail(
        id=portfolio.id,
        manager_id=portfolio.manager_id,
        name=portfolio.name,
        description=portfolio.description,
        asset_class=portfolio.asset_class,
        strategy=portfolio.strategy,
        target_occupancy=portfolio.target_occupancy,
        market=portfolio.market,
        property_ids=portfolio.property_ids,
        created_at=portfolio.created_at.isoformat(),
    )


@router.patch("/{portfolio_id}", response_model=PortfolioDetail)
async def update_portfolio(
    portfolio_id: str,
    body: UpdatePortfolioRequest,
    ps: PropertyStore = Depends(get_property_store),
) -> PortfolioDetail:
    portfolio = await ps.get_portfolio(portfolio_id)
    if not portfolio:
        raise NotFoundError("Portfolio", portfolio_id)

    updates: dict[str, object] = {}
    if body.name is not None:
        updates["name"] = body.name
    if body.description is not None:
        updates["description"] = body.description
    if body.asset_class is not None:
        updates["asset_class"] = body.asset_class
    if body.strategy is not None:
        updates["strategy"] = body.strategy
    if body.target_occupancy is not None:
        updates["target_occupancy"] = body.target_occupancy
    if body.market is not None:
        updates["market"] = body.market

    updated = portfolio.model_copy(update=updates)
    await ps.upsert_portfolio(updated)

    return PortfolioDetail(
        id=updated.id,
        manager_id=updated.manager_id,
        name=updated.name,
        description=updated.description,
        asset_class=updated.asset_class,
        strategy=updated.strategy,
        target_occupancy=updated.target_occupancy,
        market=updated.market,
        property_ids=updated.property_ids,
        created_at=updated.created_at.isoformat(),
    )


@router.get("/{portfolio_id}/summary", response_model=PortfolioSummaryResult)
async def portfolio_summary(
    portfolio_id: str,
    svc: PortfolioQueryService = Depends(get_portfolio_query),
) -> PortfolioSummaryResult:
    result = await svc.portfolio_summary(portfolio_id)
    if not result:
        raise NotFoundError("Portfolio", portfolio_id)
    return result
