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

def properties(portfolio_id=None, as_df=False):
    """List all properties. Returns list of dicts."""
    data = _get(f"/properties{_qs(portfolio_id=portfolio_id)}")
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

def maintenance(property_id=None, status=None, as_df=False):
    """List maintenance requests with optional filters."""
    data = _get(f"/maintenance{_qs(property_id=property_id, status=status)}")
    result = data.get("requests", data)
    return _maybe_df(result, as_df)


def maintenance_summary(property_id=None):
    """Get maintenance summary stats (counts by status/category, total cost)."""
    return _get(f"/maintenance/summary{_qs(property_id=property_id)}")


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
    """Portfolio-wide overview (or filtered to one manager)."""
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
'''
