"""Tests for RemoteKnowledgeGraph — validates the typed HTTP client
against a real (in-process) REMI API via TestClient.

Proves the contract: RemoteKnowledgeGraph is a drop-in replacement for
BridgedKnowledgeGraph across the full KnowledgeGraph interface.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from remi.api.dependencies import get_container
from remi.api.main import create_app
from remi.config.container import Container
from remi.knowledge.ontology.remote import RemoteKnowledgeGraph
from remi.models.ontology import KnowledgeProvenance, ObjectTypeDef, PropertyDef


@pytest.fixture
async def container() -> Container:
    c = Container()
    await c.ensure_bootstrapped()
    return c


@pytest.fixture
async def http_client(container: Container) -> AsyncClient:
    app = create_app()
    app.dependency_overrides[get_container] = lambda: container

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac  # type: ignore[misc]


@pytest.fixture
def remote_store(http_client: AsyncClient) -> RemoteKnowledgeGraph:
    return RemoteKnowledgeGraph(base_url="http://test", client=http_client)


# -- Schema round-trip --------------------------------------------------------


async def test_list_object_types(remote_store: RemoteKnowledgeGraph) -> None:
    types = await remote_store.list_object_types()
    assert isinstance(types, list)
    for t in types:
        assert isinstance(t, ObjectTypeDef)


async def test_get_object_type_found(
    remote_store: RemoteKnowledgeGraph, container: Container
) -> None:
    local_types = await container.knowledge_graph.list_object_types()
    if not local_types:
        pytest.skip("No types after bootstrap")

    name = local_types[0].name
    result = await remote_store.get_object_type(name)
    assert result is not None
    assert result.name == name


async def test_get_object_type_not_found(remote_store: RemoteKnowledgeGraph) -> None:
    result = await remote_store.get_object_type("ZZZDoesNotExist")
    assert result is None


async def test_define_then_get_object_type(remote_store: RemoteKnowledgeGraph) -> None:
    type_def = ObjectTypeDef(
        name="RemoteTestType",
        description="Defined via RemoteKnowledgeGraph",
        properties=(PropertyDef(name="x", data_type="integer"),),
        provenance=KnowledgeProvenance.USER_STATED,
    )
    await remote_store.define_object_type(type_def)

    result = await remote_store.get_object_type("RemoteTestType")
    assert result is not None
    assert result.name == "RemoteTestType"
    assert len(result.properties) == 1


# -- Search round-trip --------------------------------------------------------


async def test_search_objects_empty(remote_store: RemoteKnowledgeGraph) -> None:
    results = await remote_store.search_objects("PropertyManager")
    assert isinstance(results, list)


async def test_search_with_filters(remote_store: RemoteKnowledgeGraph) -> None:
    results = await remote_store.search_objects(
        "Unit", filters={"status": "vacant"}, limit=5
    )
    assert isinstance(results, list)


# -- Get round-trip -----------------------------------------------------------


async def test_get_object_not_found(remote_store: RemoteKnowledgeGraph) -> None:
    result = await remote_store.get_object("Property", "doesnt-exist")
    assert result is None


# -- Related round-trip -------------------------------------------------------


async def test_get_links_empty(remote_store: RemoteKnowledgeGraph) -> None:
    links = await remote_store.get_links("nonexistent-id")
    assert isinstance(links, list)
    assert len(links) == 0


async def test_traverse_empty(remote_store: RemoteKnowledgeGraph) -> None:
    nodes = await remote_store.traverse("nonexistent-id", max_depth=2)
    assert isinstance(nodes, list)


# -- Aggregate round-trip -----------------------------------------------------


async def test_aggregate_count(remote_store: RemoteKnowledgeGraph) -> None:
    result = await remote_store.aggregate("PropertyManager", "count")
    assert result == 0


# -- Timeline round-trip ------------------------------------------------------


async def test_get_timeline_empty(remote_store: RemoteKnowledgeGraph) -> None:
    events = await remote_store.get_timeline("Property", "prop-1")
    assert isinstance(events, list)


# -- Codify round-trip --------------------------------------------------------


async def test_codify_returns_entity_id(remote_store: RemoteKnowledgeGraph) -> None:
    entity_id = await remote_store.codify(
        "observation",
        {"description": "test via remote store"},
        provenance=KnowledgeProvenance.INFERRED,
    )
    assert isinstance(entity_id, str)
    assert entity_id.startswith("observation:")


# -- Contract parity: remote matches local ------------------------------------


async def test_schema_parity(
    remote_store: RemoteKnowledgeGraph, container: Container
) -> None:
    """RemoteKnowledgeGraph returns the same types as the local store."""
    local_types = await container.knowledge_graph.list_object_types()
    remote_types = await remote_store.list_object_types()

    local_names = {t.name for t in local_types}
    remote_names = {t.name for t in remote_types}
    assert local_names == remote_names


async def test_aggregate_parity(
    remote_store: RemoteKnowledgeGraph, container: Container
) -> None:
    """Aggregate results match between local and remote."""
    local_result = await container.knowledge_graph.aggregate("PropertyManager", "count")
    remote_result = await remote_store.aggregate("PropertyManager", "count")
    assert local_result == remote_result
