---
name: delinquency-review
description: Detailed delinquency analysis — delinquent tenants with balances, trends, and recommended actions.
tags: [delinquency, collections, tenants]
scope: entity
trigger: on_demand
required_capabilities: [bash]
---

# Delinquency Review

Use this when asked about delinquent tenants, overdue rent, collections
status, or anything related to accounts receivable.

## Knowledge

Key delinquency metrics:
- **Total delinquent count** — number of tenants with past-due balances
- **Total balance** — aggregate amount owed
- **0-30 day balance** — recent delinquency, may resolve
- **30+ day balance** — chronic delinquency, needs action
- **Trend direction** — improving or worsening over time

Sort tenants by highest balance first. For each tenant, note
the property, unit, and any existing action items or notes.
Recommend follow-up actions for tenants without existing plans.

## Commands

1. **Get the delinquency board** (optionally scoped to a manager):

```bash
remi operations delinquency --manager-id <manager-id>
```

Or portfolio-wide:

```bash
remi operations delinquency
```

2. **Get delinquency trends** to understand direction:

```bash
remi intelligence trends delinquency --manager-id <manager-id>
```

3. **Search for tenant context** if needed:

```bash
remi intelligence search "<tenant name>"
```

4. **Create action items** for tenants without follow-up plans:

```bash
remi operations create-action --title "Follow up on overdue rent" --manager-id <id> --priority high --tenant-id <id>
```
