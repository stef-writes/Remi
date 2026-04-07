"""Auto-generated data bridge written into every sandbox session.

``DATA_BRIDGE_SOURCE`` is a Python source string that becomes ``remi_data.py``
in the sandbox working directory.  It uses **only stdlib** (``urllib.request``,
``json``, ``os``) so it works even when pandas is not installed.  When pandas
*is* available, each function can return a DataFrame via the ``as_df`` flag.
"""

from __future__ import annotations

DATA_BRIDGE_SOURCE = '''\
"""remi_data — query the live REMI platform from sandbox Python code.

Every function hits the REMI REST API and returns plain Python dicts/lists.
Pass ``as_df=True`` to get a pandas DataFrame instead (requires pandas).

Usage::

    import remi_data

    props = remi_data.properties()
    units = remi_data.units(status="vacant")
    roll  = remi_data.rent_roll("prop-001")

    # With pandas
    import remi_data
    df = remi_data.leases(as_df=True)
    print(df.groupby("status")["rent"].mean())
"""

import json
import os
import urllib.request
import urllib.error

API = os.environ.get("REMI_API_URL", "http://127.0.0.1:8000")


def _get(path):
    """GET ``{API}/api/v1{path}`` and return parsed JSON."""
    url = f"{API}/api/v1{path}"
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as exc:
        raise ConnectionError(f"Cannot reach REMI API at {url}: {exc}") from exc


def _qs(**kwargs):
    """Build a query string from non-None kwargs."""
    pairs = [f"{k}={v}" for k, v in kwargs.items() if v is not None]
    return ("?" + "&".join(pairs)) if pairs else ""


def _maybe_df(data, as_df):
    if not as_df:
        return data
    try:
        import pandas as pd
        return pd.DataFrame(data)
    except ImportError:
        raise ImportError("pandas is required for as_df=True — install it with: pip install pandas")


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------

def properties(manager_id=None, owner_id=None, as_df=False):
    """List all properties. Returns list of dicts."""
    data = _get(f"/properties{_qs(manager_id=manager_id, owner_id=owner_id)}")
    result = data.get("properties", data)
    return _maybe_df(result, as_df)


def property_detail(property_id):
    """Get detailed info for a single property (includes unit summaries)."""
    return _get(f"/properties/{property_id}")


def rent_roll(property_id, as_df=False):
    """Get the full rent roll for a property — units, leases, tenants, maintenance."""
    data = _get(f"/properties/{property_id}/rent-roll")
    if as_df:
        return _maybe_df(data.get("rows", []), True)
    return data


# ---------------------------------------------------------------------------
# Units
# ---------------------------------------------------------------------------

def units(property_id=None, status=None, as_df=False):
    """List units across all properties, with optional filters."""
    data = _get(f"/units{_qs(property_id=property_id, status=status)}")
    result = data.get("units", data)
    return _maybe_df(result, as_df)


# ---------------------------------------------------------------------------
# Leases
# ---------------------------------------------------------------------------

def leases(property_id=None, status=None, as_df=False):
    """List leases with optional filters."""
    data = _get(f"/leases{_qs(property_id=property_id, status=status)}")
    result = data.get("leases", data)
    return _maybe_df(result, as_df)


def leases_expiring(days=60, as_df=False):
    """List leases expiring within the given number of days."""
    data = _get(f"/leases/expiring{_qs(days=days)}")
    result = data.get("leases", data)
    return _maybe_df(result, as_df)


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------

def maintenance(property_id=None, unit_id=None, manager_id=None, status=None, as_df=False):
    """List maintenance requests with optional filters.

    Parameters
    ----------
    property_id : str, optional
        Scope to a single property.
    unit_id : str, optional
        Scope to a single unit.
    manager_id : str, optional
        Scope to all properties managed by this manager — the most
        common filter for portfolio-level analytics.
    status : str, optional
        Filter by status: open, in_progress, completed, cancelled.
    as_df : bool
        Return a pandas DataFrame instead of a list of dicts.

    Notes
    -----
    Each record includes: id, property_id, unit_id, title, description,
    category, priority, status, source, vendor, cost, scheduled_date,
    completed_date, created, resolved.
    Use ``completed_date`` (not ``created``) for trend analysis by work period.
    """
    qs = _qs(property_id=property_id, unit_id=unit_id, manager_id=manager_id, status=status)
    data = _get(f"/maintenance{qs}")
    result = data.get("requests", data)
    return _maybe_df(result, as_df)


def maintenance_summary(property_id=None, unit_id=None, manager_id=None):
    """Get maintenance summary stats (counts by status/category, total cost)."""
    qs = _qs(property_id=property_id, unit_id=unit_id, manager_id=manager_id)
    return _get(f"/maintenance/summary{qs}")


# ---------------------------------------------------------------------------
# Signals
# ---------------------------------------------------------------------------

def signals(severity=None, manager_id=None, property_id=None, as_df=False):
    """List active signals with optional filters."""
    data = _get(f"/signals{_qs(severity=severity, manager_id=manager_id, property_id=property_id)}")
    result = data.get("signals", data)
    return _maybe_df(result, as_df)


def signal_detail(signal_id):
    """Get a single signal with full evidence chain."""
    return _get(f"/signals/{signal_id}/explain")


# ---------------------------------------------------------------------------
# Managers
# ---------------------------------------------------------------------------

def managers(as_df=False):
    """List all property managers with summary metrics."""
    data = _get("/managers")
    result = data.get("managers", data)
    return _maybe_df(result, as_df)


def manager_rankings(sort_by="delinquency_rate", ascending=False, limit=None, as_df=False):
    """Pre-sorted manager comparison table — avoids N+1 per-manager lookups.

    Parameters
    ----------
    sort_by : str
        Field to sort by (default "delinquency_rate"). Available:
        occupancy_rate, total_delinquent_balance, delinquency_rate,
        total_loss_to_lease, total_vacancy_loss, open_maintenance, etc.
    ascending : bool
        Sort ascending (default False = worst first).
    limit : int, optional
        Return only the top N managers.
    as_df : bool
        Return a pandas DataFrame instead of a list of dicts.
    """
    data = _get(f"/managers/rankings{_qs(sort_by=sort_by, ascending=ascending, limit=limit)}")
    result = data.get("rankings", data)
    return _maybe_df(result, as_df)


def manager_review(manager_id):
    """Get a detailed review for a specific manager."""
    return _get(f"/managers/{manager_id}/review")


# ---------------------------------------------------------------------------
# Tenants
# ---------------------------------------------------------------------------

def tenant_detail(tenant_id):
    """Look up a tenant by ID with lease history."""
    return _get(f"/tenants/{tenant_id}")


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

def dashboard_overview(manager_id=None):
    """Overview of all managed properties (or filtered to one manager)."""
    return _get(f"/dashboard/overview{_qs(manager_id=manager_id)}")


def dashboard_vacancies(manager_id=None, as_df=False):
    """Vacancy tracker across all properties."""
    data = _get(f"/dashboard/vacancies{_qs(manager_id=manager_id)}")
    result = data.get("units", data)
    return _maybe_df(result, as_df)


def dashboard_delinquency(manager_id=None, as_df=False):
    """Delinquent tenants with balances owed."""
    data = _get(f"/dashboard/delinquency{_qs(manager_id=manager_id)}")
    result = data.get("tenants", data)
    return _maybe_df(result, as_df)


# ---------------------------------------------------------------------------
# Trends (time-series)
# ---------------------------------------------------------------------------

def delinquency_trend(manager_id=None, property_id=None, periods=12, as_df=False):
    """Delinquency totals by month — returns a time-series of balance, count, avg.

    Parameters
    ----------
    manager_id : str, optional
        Filter to a specific manager's portfolio.
    property_id : str, optional
        Filter to a single property.
    periods : int
        Number of monthly periods to return (default 12).
    as_df : bool
        Return a pandas DataFrame of the ``periods`` list.
    """
    data = _get(f"/dashboard/trends/delinquency{_qs(manager_id=manager_id, property_id=property_id, periods=periods)}")
    if as_df:
        return _maybe_df(data.get("periods", []), True)
    return data


def occupancy_trend(manager_id=None, property_id=None, periods=12, as_df=False):
    """Occupancy rate by month — units occupied vs total.

    Parameters
    ----------
    manager_id : str, optional
        Filter to a specific manager's portfolio.
    property_id : str, optional
        Filter to a single property.
    periods : int
        Number of monthly periods to return (default 12).
    as_df : bool
        Return a pandas DataFrame of the ``periods`` list.
    """
    data = _get(f"/dashboard/trends/occupancy{_qs(manager_id=manager_id, property_id=property_id, periods=periods)}")
    if as_df:
        return _maybe_df(data.get("periods", []), True)
    return data


def rent_trend(manager_id=None, property_id=None, periods=12, as_df=False):
    """Average and total rent by month across active leases.

    Parameters
    ----------
    manager_id : str, optional
        Filter to a specific manager's portfolio.
    property_id : str, optional
        Filter to a single property.
    periods : int
        Number of monthly periods to return (default 12).
    as_df : bool
        Return a pandas DataFrame of the ``periods`` list.
    """
    data = _get(f"/dashboard/trends/rent{_qs(manager_id=manager_id, property_id=property_id, periods=periods)}")
    if as_df:
        return _maybe_df(data.get("periods", []), True)
    return data


# ---------------------------------------------------------------------------
# Mutations (POST/PATCH/DELETE)
# ---------------------------------------------------------------------------

def _post(path, body=None):
    """POST ``{API}/api/v1{path}`` with a JSON body and return parsed JSON."""
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
    except urllib.error.URLError as exc:
        raise ConnectionError(f"Cannot reach REMI API at {url}: {exc}") from exc


def create_action(
    manager_id, title, description="", priority="medium",
    due_date=None, entity_type=None, entity_id=None,
):
    """Create an action item for a manager.

    Parameters
    ----------
    manager_id : str
        The manager this action is for.
    title : str
        Short action title.
    description : str
        Detailed description.
    priority : str
        One of: urgent, high, medium, low.
    due_date : str, optional
        Due date as YYYY-MM-DD.
    entity_type : str, optional
        Related entity type (e.g. "Tenant", "Property").
    entity_id : str, optional
        Related entity ID.
    """
    body = {
        "manager_id": manager_id,
        "title": title,
        "description": description,
        "priority": priority,
    }
    if due_date:
        body["due_date"] = due_date
    if entity_type:
        body["entity_type"] = entity_type
    if entity_id:
        body["entity_id"] = entity_id
    return _post("/actions", body)


def create_note(content, entity_type=None, entity_id=None, tags=None):
    """Create a note, optionally linked to an entity.

    Parameters
    ----------
    content : str
        Note content.
    entity_type : str, optional
        Related entity type.
    entity_id : str, optional
        Related entity ID.
    tags : list, optional
        Tags for the note.
    """
    body = {"content": content}
    if entity_type:
        body["entity_type"] = entity_type
    if entity_id:
        body["entity_id"] = entity_id
    if tags:
        body["tags"] = tags
    return _post("/notes", body)


def search(query, types=None, manager_id=None, limit=10, as_df=False):
    """Hybrid keyword + semantic search across all entities.

    Fast, deterministic — no LLM involved. Useful for finding managers,
    properties, tenants, units, or maintenance requests by name, address,
    or natural language description.

    Parameters
    ----------
    query : str
        Search query — a name, address, description, or natural language phrase.
    types : str or list, optional
        Comma-separated (or list) of entity types to filter:
        PropertyManager, Property, Tenant, Unit, MaintenanceRequest, DocumentRow.
    manager_id : str, optional
        Scope results to a specific manager's entities.
    limit : int
        Max results to return (default 10, max 50).
    as_df : bool
        Return a pandas DataFrame instead of a list of dicts.

    Returns
    -------
    list[dict] or DataFrame
        Each hit has: entity_id, entity_type, label, title, subtitle, score, metadata.
    """
    params = {"q": query, "limit": limit}
    if types:
        if isinstance(types, list):
            types = ",".join(types)
        params["types"] = types
    if manager_id:
        params["manager_id"] = manager_id
    data = _get(f"/search{_qs(**params)}")
    results = data.get("results", data)
    return _maybe_df(results, as_df)


def trigger_signal_inference():
    """Trigger the signal inference pipeline to re-evaluate all signals.

    NOTE: The precomputed signal engine has been removed. Signals are now
    evaluated on demand by the agent. This function is a no-op stub.
    """
    import warnings
    warnings.warn(
        "trigger_signal_inference is a no-op — signals are evaluated on demand by the agent",
        stacklevel=2,
    )
    return {"status": "noop", "message": "signal inference removed — agent evaluates on demand"}
'''
