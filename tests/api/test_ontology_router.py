"""Tests for the ontology REST API router.

Uses FastAPI's TestClient with dependency overrides to inject a
bootstrapped Container with in-memory stores.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from remi.models.ontology import KnowledgeProvenance, ObjectTypeDef, PropertyDef
from remi.config.container import Container
from remi.api.dependencies import get_container
from remi.api.main import create_app


@pytest.fixture
async def container() -> Container:
    c = Container()
    await c.ensure_bootstrapped()
    return c


@pytest.fixture
async def client(container: Container) -> AsyncClient:
    app = create_app()
    app.dependency_overrides[get_container] = lambda: container

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac  # type: ignore[misc]


# -- schema endpoints --------------------------------------------------------


async def test_list_schema(client: AsyncClient, container: Container) -> None:
    resp = await client.get("/api/v1/ontology/schema")
    assert resp.status_code == 200
    data = resp.json()
    assert "types" in data
    assert "link_types" in data
    assert isinstance(data["types"], list)


async def test_get_schema_type_found(client: AsyncClient, container: Container) -> None:
    types = await container.ontology_store.list_object_types()
    if not types:
        pytest.skip("No types registered after bootstrap")

    name = types[0].name
    resp = await client.get(f"/api/v1/ontology/schema/{name}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"]["name"] == name


async def test_get_schema_type_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/ontology/schema/NonExistentType")
    assert resp.status_code == 404


# -- search endpoints --------------------------------------------------------


async def test_search_objects_empty(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/ontology/search/PropertyManager")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["objects"] == []


async def test_search_objects_post_with_filters(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/ontology/search/Unit", json={
        "filters": {"status": "vacant"},
        "limit": 10,
    })
    assert resp.status_code == 200
    assert "objects" in resp.json()


# -- get endpoint -------------------------------------------------------------


async def test_get_object_not_found(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/ontology/objects/Property/doesnt-exist")
    assert resp.status_code == 404


# -- related endpoint ---------------------------------------------------------


async def test_related_no_links(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/ontology/related/some-id")
    assert resp.status_code == 200
    data = resp.json()
    assert data["object_id"] == "some-id"
    assert data["count"] == 0


async def test_related_with_depth(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/ontology/related/some-id?max_depth=3")
    assert resp.status_code == 200
    data = resp.json()
    assert data["depth"] == 3


# -- aggregate endpoint -------------------------------------------------------


async def test_aggregate_count(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/ontology/aggregate/PropertyManager", json={
        "metric": "count",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["type_name"] == "PropertyManager"
    assert data["metric"] == "count"
    assert data["result"] == 0


# -- timeline endpoint --------------------------------------------------------


async def test_timeline_empty(client: AsyncClient) -> None:
    resp = await client.get("/api/v1/ontology/timeline/Property/prop-1")
    assert resp.status_code == 200
    data = resp.json()
    assert data["count"] == 0
    assert data["events"] == []


# -- codify endpoint ----------------------------------------------------------


async def test_codify_observation(client: AsyncClient) -> None:
    resp = await client.post("/api/v1/ontology/codify", json={
        "knowledge_type": "observation",
        "data": {"description": "Test observation from API"},
        "provenance": "inferred",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["knowledge_type"] == "observation"
    assert data["entity_id"].startswith("observation:")


async def test_codify_with_link(client: AsyncClient, container: Container) -> None:
    resp = await client.post("/api/v1/ontology/codify", json={
        "knowledge_type": "causal_link",
        "data": {"description": "Cause and effect"},
        "source_id": "entity-a",
        "target_id": "entity-b",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True

    links = await container.ontology_store.get_links("entity-a")
    assert any(lnk["link_type"] == "CAUSES" for lnk in links)


# -- define endpoint ----------------------------------------------------------


async def test_define_type(client: AsyncClient, container: Container) -> None:
    resp = await client.post("/api/v1/ontology/define", json={
        "name": "TestWidget",
        "description": "A test widget type",
        "properties": [
            {"name": "color", "data_type": "string"},
            {"name": "weight", "data_type": "decimal", "required": True},
        ],
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["type"]["name"] == "TestWidget"

    ot = await container.ontology_store.get_object_type("TestWidget")
    assert ot is not None
    assert len(ot.properties) == 2
    assert ot.provenance == KnowledgeProvenance.USER_STATED
