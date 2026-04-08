---
name: portfolio-health
description: Complete portfolio health check — red flags, occupancy, delinquency, vacancies, lease risk, worst-performing managers.
tags: [portfolio, dashboard, health, overview]
scope: global
trigger: on_demand
required_capabilities: [bash]
---

# Portfolio Health Check

Use this when asked about overall portfolio status, problems, or
"what needs attention." No parameters needed — this is a full sweep.

## Knowledge

Red flags to surface (in priority order):
- Portfolio occupancy below 90%
- Any delinquent tenants (count + total balance)
- Vacant units (count + monthly rent at risk)
- Leases expiring in 90 days (count + revenue at risk)
- Managers with significantly worse metrics than portfolio average

Present red flags first, then overview numbers, then the
worst-performing managers. Give the director an immediate
sense of what needs attention and who to talk to.

## Commands

1. **Dashboard overview** — top-level portfolio metrics:

```bash
remi intelligence dashboard
```

2. **Delinquency board** — all delinquent tenants:

```bash
remi operations delinquency
```

3. **Vacancies** — all vacant units:

```bash
remi intelligence vacancies
```

4. **Expiring leases** — leases ending in 90 days:

```bash
remi operations expiring-leases --days 90
```

5. **Rank managers** by worst delinquency rate:

```bash
remi portfolio rankings --sort-by delinquency_rate --limit 5
```
