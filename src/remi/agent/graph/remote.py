"""RemoteKnowledgeGraph — KnowledgeGraph adapter that delegates to the REMI API.

Drop-in replacement for BridgedKnowledgeGraph: any code that takes a
KnowledgeGraph works identically whether backed by local stores or by
HTTP calls to a running REMI server.

Used by:
  - CLI commands running in the agent sandbox (via REMI_API_URL)
  - Any external process that needs typed knowledge graph access
"""

from __future__ import annotations

from typing import Any

import httpx

from remi.agent.graph.stores import KnowledgeGraph
from remi.agent.graph.types import (
    AggregateResult,
    GraphLink,
    GraphObject,
    KnowledgeProvenance,
    LinkTypeDef,
    ObjectTypeDef,
    TimelineEvent,
)


class RemoteKnowledgeGraph(KnowledgeGraph):
    """KnowledgeGraph implementation over HTTP — calls the knowledge graph REST API."""

    def __init__(
        self,
        base_url: str,
        client: httpx.AsyncClient | None = None,
        *,
        timeout: float = 30.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._prefix = f"{self._base}/api/v1/ontology"
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def __aenter__(self) -> RemoteKnowledgeGraph:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()

    # -- Schema ---------------------------------------------------------------

    async def list_object_types(self) -> list[ObjectTypeDef]:
        data = await self._get("/schema")
        return [ObjectTypeDef.model_validate(t) for t in data["types"]]

    async def get_object_type(self, name: str) -> ObjectTypeDef | None:
        resp = await self._client.get(f"{self._prefix}/schema/{name}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return ObjectTypeDef.model_validate(resp.json()["type"])

    async def define_object_type(self, type_def: ObjectTypeDef) -> None:
        props = [
            {
                "name": p.name,
                "data_type": p.data_type,
                "required": p.required,
                "description": p.description,
            }
            for p in type_def.properties
        ]
        await self._post(
            "/define",
            {
                "name": type_def.name,
                "description": type_def.description,
                "properties": props,
                "provenance": type_def.provenance.value,
            },
        )

    async def list_link_types(self) -> list[LinkTypeDef]:
        data = await self._get("/schema")
        return [LinkTypeDef.model_validate(lt) for lt in data["link_types"]]

    async def define_link_type(self, link_def: LinkTypeDef) -> None:
        raise NotImplementedError("define_link_type not exposed via REST API yet")

    # -- Objects --------------------------------------------------------------

    async def get_object(self, type_name: str, object_id: str) -> GraphObject | None:
        resp = await self._client.get(f"{self._prefix}/objects/{type_name}/{object_id}")
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        raw = resp.json()["object"]
        if raw is None:
            return None
        return GraphObject.model_validate(raw)

    async def search_objects(
        self,
        type_name: str,
        *,
        filters: dict[str, Any] | None = None,
        order_by: str | None = None,
        limit: int = 50,
    ) -> list[GraphObject]:
        if filters:
            data = await self._post(
                f"/search/{type_name}",
                {
                    "filters": filters,
                    "order_by": order_by,
                    "limit": limit,
                },
            )
        else:
            params: dict[str, Any] = {"limit": limit}
            if order_by:
                params["order_by"] = order_by
            data = await self._get(f"/search/{type_name}", params=params)
        return [GraphObject.model_validate(obj) for obj in data["objects"]]

    async def put_object(self, type_name: str, object_id: str, properties: dict[str, Any]) -> None:
        raise NotImplementedError("put_object not exposed via REST API yet")

    async def delete_object(self, type_name: str, object_id: str) -> bool:
        raise NotImplementedError("delete_object not exposed via REST API yet")

    # -- Links ----------------------------------------------------------------

    async def get_links(
        self,
        object_id: str,
        *,
        link_type: str | None = None,
        direction: str = "both",
    ) -> list[GraphLink]:
        params: dict[str, Any] = {"direction": direction, "max_depth": 1}
        if link_type:
            params["link_type"] = link_type
        data = await self._get(f"/related/{object_id}", params=params)
        return [GraphLink.model_validate(link) for link in data["links"]]

    async def put_link(
        self,
        source_id: str,
        link_type: str,
        target_id: str,
        *,
        properties: dict[str, Any] | None = None,
    ) -> None:
        raise NotImplementedError("put_link not exposed via REST API yet")

    async def traverse(
        self,
        start_id: str,
        link_types: list[str] | None = None,
        *,
        max_depth: int = 3,
    ) -> list[GraphObject]:
        params: dict[str, Any] = {"max_depth": max_depth}
        if link_types and len(link_types) == 1:
            params["link_type"] = link_types[0]
        data = await self._get(f"/related/{start_id}", params=params)
        return [GraphObject.model_validate(node) for node in data["nodes"]]

    # -- Aggregation ----------------------------------------------------------

    async def aggregate(
        self,
        type_name: str,
        metric: str,
        field: str | None = None,
        *,
        filters: dict[str, Any] | None = None,
        group_by: str | None = None,
    ) -> AggregateResult:
        data = await self._post(
            f"/aggregate/{type_name}",
            {
                "metric": metric,
                "field": field,
                "filters": filters,
                "group_by": group_by,
            },
        )
        raw = data["result"]
        if isinstance(raw, dict):
            return AggregateResult(groups=raw)
        return AggregateResult(value=raw)

    # -- Timeline -------------------------------------------------------------

    async def record_event(
        self,
        object_type: str,
        object_id: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        raise NotImplementedError("record_event not exposed via REST API yet")

    async def get_timeline(
        self,
        object_type: str,
        object_id: str,
        *,
        event_types: list[str] | None = None,
        limit: int = 50,
    ) -> list[TimelineEvent]:
        params: dict[str, Any] = {"limit": limit}
        if event_types:
            params["event_types"] = ",".join(event_types)
        data = await self._get(f"/timeline/{object_type}/{object_id}", params=params)
        return [
            TimelineEvent(
                id=evt.get("id", ""),
                event_type=evt.get("event_type", ""),
                object_type=object_type,
                object_id=object_id,
                timestamp=evt.get("timestamp", ""),
                data=evt.get("data", {}),
            )
            for evt in data["events"]
        ]

    # -- Knowledge codification -----------------------------------------------

    async def codify(
        self,
        knowledge_type: str,
        data: dict[str, Any],
        *,
        provenance: KnowledgeProvenance = KnowledgeProvenance.INFERRED,
    ) -> str:
        resp = await self._post(
            "/codify",
            {
                "knowledge_type": knowledge_type,
                "data": data,
                "provenance": provenance.value,
            },
        )
        return resp["entity_id"]

    # -- HTTP helpers ---------------------------------------------------------

    async def _get(self, path: str, *, params: dict[str, Any] | None = None) -> dict[str, Any]:
        resp = await self._client.get(f"{self._prefix}{path}", params=params)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    async def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        resp = await self._client.post(f"{self._prefix}{path}", json=body)
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]
