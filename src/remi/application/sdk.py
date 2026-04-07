"""remi — clean SDK for querying the REMI platform from sandbox Python code.

Flat namespace: ``import remi`` then ``remi.managers()``, ``remi.leases()``, etc.
Every function returns plain Python dicts/lists.  Pass ``as_df=True`` for a
pandas DataFrame.  Name resolution is built in — pass names, not IDs.

Uses only stdlib (``urllib``, ``json``, ``os``).

This module is a real ``.py`` file (lintable, testable) that gets copied into
the sandbox working directory at session start.
"""

import json
import os
import urllib.error
import urllib.request

API = os.environ.get("REMI_API_URL", "http://127.0.0.1:8000")


def _get(path):
    url = f"{API}/api/v1{path}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"REMI API error {exc.code} on {url}: {body}") from exc
    except urllib.error.URLError as exc:
        raise ConnectionError(f"Cannot reach REMI API at {url}: {exc}") from exc


def _post(path, body=None):
    url = f"{API}/api/v1{path}"
    data = json.dumps(body or {}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Accept": "application/json", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"REMI API error {exc.code} on {url}: {body_text}") from exc
    except urllib.error.URLError as exc:
        raise ConnectionError(f"Cannot reach REMI API at {url}: {exc}") from exc


def _qs(**kwargs):
    pairs = [f"{k}={v}" for k, v in kwargs.items() if v is not None]
    return ("?" + "&".join(pairs)) if pairs else ""


def _df(data):
    try:
        import pandas as pd
        return pd.DataFrame(data)
    except ImportError:
        raise ImportError("pandas required for as_df=True — pip install pandas") from None


# ── Name resolution ─────────────────────────────────────────────────────────

def _resolve_manager(name_or_id):
    """Accept a manager name or ID; return the ID."""
    if not name_or_id:
        return None
    mgrs = _get("/managers").get("managers", [])
    for m in mgrs:
        if m.get("id") == name_or_id:
            return name_or_id
        if m.get("name", "").lower() == str(name_or_id).lower():
            return m["id"]
    return name_or_id


def _resolve_property(name_or_id):
    """Accept a property name/address or ID; return the ID."""
    if not name_or_id:
        return None
    props = _get("/properties").get("properties", [])
    needle = str(name_or_id).lower()
    for p in props:
        if p.get("id") == name_or_id:
            return name_or_id
        if p.get("name", "").lower() == needle or p.get("address", "").lower() == needle:
            return p["id"]
    return name_or_id


# ── Portfolio ───────────────────────────────────────────────────────────────

def managers(as_df=False):
    """All property managers with summary metrics."""
    data = _get("/managers").get("managers", [])
    return _df(data) if as_df else data


def manager_review(manager, as_df=False):
    """Deep review for a manager (name or ID)."""
    mid = _resolve_manager(manager)
    data = _get(f"/managers/{mid}/review")
    return _df([data]) if as_df else data


def manager_rankings(sort_by="delinquency_rate", ascending=False, limit=None, as_df=False):
    """Sorted manager comparison table."""
    data = _get(f"/managers/rankings{_qs(sort_by=sort_by, ascending=ascending, limit=limit)}")
    rows = data.get("rankings", data)
    return _df(rows) if as_df else rows


def properties(manager=None, as_df=False):
    """All properties, optionally filtered by manager (name or ID)."""
    mid = _resolve_manager(manager)
    data = _get(f"/properties{_qs(manager_id=mid)}").get("properties", [])
    return _df(data) if as_df else data


def property_detail(property_name_or_id):
    """Detailed info for a single property (includes unit summaries)."""
    pid = _resolve_property(property_name_or_id)
    return _get(f"/properties/{pid}")


def units(property_name_or_id=None, status=None, as_df=False):
    """All units, optionally filtered by property and/or status."""
    pid = _resolve_property(property_name_or_id)
    data = _get(f"/units{_qs(property_id=pid, status=status)}").get("units", [])
    return _df(data) if as_df else data


def rent_roll(property_name_or_id, as_df=False):
    """Full rent roll for a property — units, leases, tenants, maintenance."""
    pid = _resolve_property(property_name_or_id)
    data = _get(f"/properties/{pid}/rent-roll")
    if as_df:
        return _df(data.get("rows", []))
    return data


# ── Operations ──────────────────────────────────────────────────────────────

def leases(property_name_or_id=None, status=None, as_df=False):
    """All leases, optionally filtered."""
    pid = _resolve_property(property_name_or_id)
    data = _get(f"/leases{_qs(property_id=pid, status=status)}").get("leases", [])
    return _df(data) if as_df else data


def leases_expiring(days=60, as_df=False):
    """Leases expiring within *days* days."""
    data = _get(f"/leases/expiring{_qs(days=days)}").get("leases", [])
    return _df(data) if as_df else data


def maintenance(manager=None, property_name_or_id=None, status=None, as_df=False):
    """Maintenance requests with optional filters."""
    mid = _resolve_manager(manager)
    pid = _resolve_property(property_name_or_id)
    data = _get(
        f"/maintenance{_qs(manager_id=mid, property_id=pid, status=status)}"
    ).get("requests", [])
    return _df(data) if as_df else data


def maintenance_summary(manager=None, property_name_or_id=None):
    """Maintenance summary stats (counts by status/category, total cost)."""
    mid = _resolve_manager(manager)
    pid = _resolve_property(property_name_or_id)
    return _get(f"/maintenance/summary{_qs(manager_id=mid, property_id=pid)}")


def tenants(tenant_id=None):
    """Look up a tenant by ID with lease history."""
    return _get(f"/tenants/{tenant_id}")


# ── Dashboard ───────────────────────────────────────────────────────────────

def overview(manager=None):
    """Portfolio overview — all managed properties (or filtered to one manager)."""
    mid = _resolve_manager(manager)
    return _get(f"/dashboard/overview{_qs(manager_id=mid)}")


def vacancies(manager=None, as_df=False):
    """Vacancy tracker across all properties."""
    mid = _resolve_manager(manager)
    data = _get(f"/dashboard/vacancies{_qs(manager_id=mid)}").get("units", [])
    return _df(data) if as_df else data


def delinquencies(manager=None, as_df=False):
    """Delinquent tenants with balances owed."""
    mid = _resolve_manager(manager)
    data = _get(f"/dashboard/delinquency{_qs(manager_id=mid)}").get("tenants", [])
    return _df(data) if as_df else data


# ── Trends ──────────────────────────────────────────────────────────────────

def trends(metric="delinquency", manager=None, property_name_or_id=None, periods=12, as_df=False):
    """Time-series trends. *metric* is one of: delinquency, occupancy, rent, maintenance."""
    mid = _resolve_manager(manager)
    pid = _resolve_property(property_name_or_id)
    data = _get(
        f"/dashboard/trends/{metric}{_qs(manager_id=mid, property_id=pid, periods=periods)}"
    )
    rows = data.get("periods", [])
    return _df(rows) if as_df else rows


# ── Search ──────────────────────────────────────────────────────────────────

def search(query, types=None, manager=None, limit=10, as_df=False):
    """Hybrid keyword + semantic search across all entities."""
    mid = _resolve_manager(manager)
    params = {"q": query, "limit": limit}
    if types:
        if isinstance(types, list):
            types = ",".join(types)
        params["types"] = types
    if mid:
        params["manager_id"] = mid
    data = _get(f"/search{_qs(**params)}").get("results", [])
    return _df(data) if as_df else data


# ── Mutations ───────────────────────────────────────────────────────────────

def create_action(manager, title, description="", priority="medium",
                  due_date=None, entity_type=None, entity_id=None):
    """Create an action item for a manager (name or ID)."""
    mid = _resolve_manager(manager)
    body = {"manager_id": mid, "title": title, "description": description, "priority": priority}
    if due_date:
        body["due_date"] = due_date
    if entity_type:
        body["entity_type"] = entity_type
    if entity_id:
        body["entity_id"] = entity_id
    return _post("/actions/items", body)


def create_note(content, entity_type=None, entity_id=None, tags=None):
    """Create a note, optionally linked to an entity."""
    body = {"content": content}
    if entity_type:
        body["entity_type"] = entity_type
    if entity_id:
        body["entity_id"] = entity_id
    if tags:
        body["tags"] = tags
    return _post("/notes", body)
