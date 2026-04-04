"""Tests for EmbeddingPipeline — text extraction and end-to-end embedding."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from remi.application.core.models import (
    Address,
    Lease,
    LeaseStatus,
    MaintenanceCategory,
    MaintenanceRequest,
    MaintenanceStatus,
    Portfolio,
    Priority,
    Property,
    PropertyManager,
    Tenant,
    TenantStatus,
    Unit,
    UnitStatus,
)
from remi.application.infra.stores.mem import InMemoryPropertyStore
from remi.agent.vectors.embedder import NoopEmbedder
from remi.application.services.embedding.pipeline import EmbeddingPipeline
from remi.agent.vectors.store import InMemoryVectorStore

_ADDR = Address(street="100 Smithfield St", city="Pittsburgh", state="PA", zip_code="15222")


@pytest.fixture
def property_store() -> InMemoryPropertyStore:
    return InMemoryPropertyStore()


@pytest.fixture
def vector_store() -> InMemoryVectorStore:
    return InMemoryVectorStore()


@pytest.fixture
def embedder() -> NoopEmbedder:
    return NoopEmbedder(dimension=32)


@pytest.fixture
def pipeline(
    property_store: InMemoryPropertyStore,
    vector_store: InMemoryVectorStore,
    embedder: NoopEmbedder,
) -> EmbeddingPipeline:
    return EmbeddingPipeline(
        property_store=property_store,
        vector_store=vector_store,
        embedder=embedder,
    )


async def _seed(ps: InMemoryPropertyStore) -> None:
    mgr = PropertyManager(id="mgr-1", name="Jake Kraus", email="jake@rivaridge.com")
    await ps.upsert_manager(mgr)

    pf = Portfolio(id="pf-1", manager_id="mgr-1", name="Kraus Portfolio")
    await ps.upsert_portfolio(pf)

    prop = Property(id="prop-1", portfolio_id="pf-1", name="100 Smithfield St", address=_ADDR)
    await ps.upsert_property(prop)

    await ps.upsert_unit(
        Unit(
            id="unit-1",
            property_id="prop-1",
            unit_number="101",
            status=UnitStatus.OCCUPIED,
            current_rent=Decimal("1200"),
            market_rent=Decimal("1400"),
            bedrooms=2,
            bathrooms=1,
            sqft=850,
        )
    )
    await ps.upsert_unit(
        Unit(
            id="unit-2",
            property_id="prop-1",
            unit_number="102",
            status=UnitStatus.VACANT,
            days_vacant=45,
        )
    )

    await ps.upsert_tenant(
        Tenant(
            id="t-1",
            name="Carlos Rivera",
            status=TenantStatus.CURRENT,
            balance_owed=Decimal("500"),
            tags=["late-payer"],
        )
    )
    await ps.upsert_lease(
        Lease(
            id="lease-1",
            tenant_id="t-1",
            property_id="prop-1",
            unit_id="unit-1",
            start_date=date(2024, 1, 1),
            end_date=date(2025, 12, 31),
            monthly_rent=Decimal("1200"),
            status=LeaseStatus.ACTIVE,
        )
    )

    await ps.upsert_maintenance_request(
        MaintenanceRequest(
            id="maint-1",
            property_id="prop-1",
            unit_id="unit-1",
            title="Leaky faucet in kitchen",
            description=(
                "Kitchen faucet has been dripping for a week. Washer likely needs replacing."
            ),
            category=MaintenanceCategory.PLUMBING,
            priority=Priority.MEDIUM,
            status=MaintenanceStatus.OPEN,
            created_at=datetime.now(UTC),
        )
    )


class TestPipelineEndToEnd:
    @pytest.mark.asyncio
    async def test_run_full_embeds_all_entity_types(
        self,
        property_store: InMemoryPropertyStore,
        vector_store: InMemoryVectorStore,
        pipeline: EmbeddingPipeline,
    ) -> None:
        await _seed(property_store)
        result = await pipeline.run_full()

        assert result.embedded > 0
        assert result.errors == 0
        assert "Tenant" in result.by_type
        assert "Unit" in result.by_type
        assert "Property" in result.by_type
        assert "MaintenanceRequest" in result.by_type

    @pytest.mark.asyncio
    async def test_empty_store_produces_zero(
        self,
        pipeline: EmbeddingPipeline,
        vector_store: InMemoryVectorStore,
    ) -> None:
        result = await pipeline.run_full()
        assert result.embedded == 0
        assert await vector_store.count() == 0

    @pytest.mark.asyncio
    async def test_vectors_are_searchable_after_pipeline(
        self,
        property_store: InMemoryPropertyStore,
        vector_store: InMemoryVectorStore,
        embedder: NoopEmbedder,
        pipeline: EmbeddingPipeline,
    ) -> None:
        await _seed(property_store)
        await pipeline.run_full()

        query_vec = await embedder.embed_one("leaky faucet kitchen")
        results = await vector_store.search(query_vec, limit=5)
        assert len(results) > 0

    @pytest.mark.asyncio
    async def test_idempotent_rerun(
        self,
        property_store: InMemoryPropertyStore,
        vector_store: InMemoryVectorStore,
        pipeline: EmbeddingPipeline,
    ) -> None:
        """Running the pipeline twice should not duplicate records."""
        await _seed(property_store)
        r1 = await pipeline.run_full()
        r2 = await pipeline.run_full()
        assert r1.embedded == r2.embedded
        assert await vector_store.count() == r2.embedded

    @pytest.mark.asyncio
    async def test_metadata_includes_manager_id(
        self,
        property_store: InMemoryPropertyStore,
        vector_store: InMemoryVectorStore,
        pipeline: EmbeddingPipeline,
    ) -> None:
        await _seed(property_store)
        await pipeline.run_full()

        rec = await vector_store.get("vec:property:prop-1:profile")
        assert rec is not None
        assert rec.metadata["manager_id"] == "mgr-1"

    @pytest.mark.asyncio
    async def test_tenant_text_includes_balance(
        self,
        property_store: InMemoryPropertyStore,
        vector_store: InMemoryVectorStore,
        pipeline: EmbeddingPipeline,
    ) -> None:
        await _seed(property_store)
        await pipeline.run_full()

        rec = await vector_store.get("vec:tenant:t-1:profile")
        assert rec is not None
        assert "500" in rec.text
        assert "Carlos Rivera" in rec.text

    @pytest.mark.asyncio
    async def test_maintenance_text_includes_description(
        self,
        property_store: InMemoryPropertyStore,
        vector_store: InMemoryVectorStore,
        pipeline: EmbeddingPipeline,
    ) -> None:
        await _seed(property_store)
        await pipeline.run_full()

        rec = await vector_store.get("vec:maintenance:maint-1:description")
        assert rec is not None
        assert "faucet" in rec.text.lower()
        assert "kitchen" in rec.text.lower()
