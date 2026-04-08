---
name: lease-risk
description: Lease expiration and vacancy risk analysis — expiring leases, month-to-month leases, current vacancies, and estimated revenue at risk.
tags: [leases, vacancies, risk, revenue]
scope: entity
trigger: on_demand
required_capabilities: [bash]
---

# Lease Risk Review

Use this when asked about lease expirations, vacancy exposure,
revenue at risk, or renewal pipeline.

## Knowledge

Revenue risk has two components:
- **Expiring leases** — active leases ending in N days. If not renewed,
  these become vacancies. Revenue at risk = sum of monthly rents.
- **Current vacancies** — already empty units losing market rent.
- **Month-to-month** — expired leases still active but not renewed.
  These tenants can leave with 30 days notice.

Prioritize by highest rent at risk first. Check occupancy trends
to see if the situation is improving or declining.

## Commands

1. **Pull expiring leases** (default 90-day window):

```bash
remi operations expiring-leases --days 90 --manager-id <manager-id>
```

2. **Pull current vacancies**:

```bash
remi intelligence vacancies --manager-id <manager-id>
```

3. **Check occupancy trends** for context:

```bash
remi intelligence trends occupancy --manager-id <manager-id>
```

4. **Get the full lease list** for detail:

```bash
remi operations leases --manager-id <manager-id>
```

## What to Report

- Number of leases expiring in 90 days and total monthly rent at risk
- Month-to-month leases (already expired but not renewed)
- Current vacant units and market rent being lost
- Combined monthly revenue exposure
- Trend direction: is occupancy improving or declining?
