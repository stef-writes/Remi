---
name: entity-search
description: Find managers, properties, tenants, units, or maintenance requests by name, address, or natural language query.
tags: [search, lookup, find]
scope: global
trigger: on_demand
required_capabilities: [bash]
---

# Entity Search

Use this when you need to find a specific entity — a manager by name,
a property by address, a tenant, or a maintenance request.

## Knowledge

Search returns entities ranked by relevance. Each result includes:
- `entity_type` — PropertyManager, Property, Tenant, Unit, etc.
- `entity_id` — use this to fetch details via other commands
- `name` — display name
- `score` — relevance score

After finding an entity, use the appropriate detail command with the
entity's ID to get full information.

## Commands

1. **Run a search**:

```bash
remi intelligence search "jake anderson"
```

2. **Use results** to get detailed data. The `entity_id` from search
   results can be passed to detail commands:

```bash
remi portfolio manager-review <entity-id>
remi portfolio properties --manager-id <entity-id>
remi operations leases --property-id <entity-id>
```

## Tips

- Search works on names, addresses, descriptions, and document content
- For listing all entities of a type, use the list commands instead:
  `remi portfolio managers`, `remi portfolio properties`, etc.
