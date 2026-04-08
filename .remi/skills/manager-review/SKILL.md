---
name: manager-review
description: Complete performance review for a property manager — summary, delinquency, lease expirations, vacancies, action items, and notes.
tags: [manager, review, performance]
scope: entity
trigger: on_demand
required_capabilities: [bash]
---

# Manager Review

Use this workflow when asked about a specific manager's performance,
portfolio, or when preparing for a manager meeting.

## Knowledge

A manager review surfaces:
- **Occupancy rate** — below 90% is a red flag
- **Delinquent balance** — total owed across all tenants, how many tenants
- **Lease expirations** — leases ending in 90 days = revenue at risk
- **Vacancies** — empty units and market rent being lost
- **Trend direction** — is the manager improving or declining?

Compare metrics to portfolio averages when possible. Highlight the
single biggest risk for this manager.

## Commands

1. **Get the full manager review** (summary + delinquency + vacancies + expirations + action items):

```bash
remi portfolio manager-review <manager-id>
```

2. **Get delinquency details** if the review shows delinquent balance:

```bash
remi operations delinquency --manager-id <manager-id>
```

3. **Get trends** to understand direction:

```bash
remi intelligence trends delinquency --manager-id <manager-id>
remi intelligence trends occupancy --manager-id <manager-id>
```

4. **Get rankings** to compare against other managers:

```bash
remi portfolio rankings --sort-by occupancy_rate
```

## Finding the Manager ID

If you have a manager name, list all managers first:

```bash
remi portfolio managers
```

Then use the `id` field from the matching manager.
