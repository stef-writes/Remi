# REMI — Real Estate Management Intelligence

A layered AI architecture for property management analytics and operations. REMI gives property managers AI-powered intelligence across their portfolios, properties, and units over time.

## Architecture

REMI uses a clean hexagonal/ports-and-adapters architecture:

```
interfaces/          CLI (typer) + REST API (FastAPI)
    |
application/         Use cases: app management, execution, state queries
    |
domain/              Entities: PropertyManager, Portfolio, Property, Unit,
    |                Lease, Tenant, MaintenanceRequest, MetricSnapshot
    |
infrastructure/      Adapters: LLM providers, in-memory stores, tools, seed data
    |
runtime/             Graph execution engine, event bus, retry policies
```

## Quick Start

```bash
# Install with dev dependencies
uv pip install -e ".[dev]"

# Run tests
python -m pytest tests/ -v

# Explore portfolios
remi portfolio list
remi portfolio summary pf-1

# Inspect properties
remi property list
remi property inspect prop-1

# Find vacant units
remi units list --status vacant

# Check expiring leases
remi leases expiring --days 60

# Maintenance dashboard
remi maintenance list --status open
remi maintenance summary

# Financial reports
remi report financial prop-1
remi report financial prop-1 2025-Q3

# Ask REMI AI (requires an LLM provider API key)
remi ask portfolio "What is the occupancy rate across all portfolios?"
remi ask property "Give me a detailed breakdown of Sunset Terrace"
remi ask maintenance "What are the most common maintenance issues?"

# Start the API server
remi serve
```

## API Endpoints

Once the server is running (`remi serve`):

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/portfolios` | List portfolios |
| GET | `/api/v1/portfolios/{id}/summary` | Portfolio summary |
| GET | `/api/v1/properties` | List properties |
| GET | `/api/v1/properties/{id}` | Property details with units |
| GET | `/api/v1/leases/expiring?days=60` | Expiring leases |
| GET | `/api/v1/maintenance?status=open` | Maintenance requests |
| GET | `/api/v1/maintenance/summary` | Maintenance summary |
| GET | `/api/v1/reports/financial/{id}` | Financial history |
| GET | `/api/v1/reports/financial/{id}/{period}` | Single period report |
| POST | `/api/v1/ask` | AI-powered question (`{"question": "...", "agent": "portfolio_analyst"}`) |

## Sample Data

REMI ships with a realistic seed dataset:

- **2 property managers** (Urban Edge Properties, Keystone Property Management)
- **3 portfolios** (Bay Area Residential, Tech Corridor Commercial, Midwest Mixed Use)
- **6 properties** across San Francisco, Oakland, San Jose, and Chicago
- **28 units** (residential, commercial, and mixed-use)
- **21 tenants** with active and expired leases
- **8 maintenance requests** across multiple categories
- **12 months of historical metrics** (occupancy, revenue, maintenance costs)
- **Quarterly financial summaries** (NOI, expenses, vacancy loss)

## AI Agents

REMI includes three YAML-declared AI agents that use the tool system:

- **Portfolio Analyst** — Answers questions about portfolio performance, occupancy trends, financial metrics
- **Property Inspector** — Deep-dives into individual properties with unit-by-unit analysis
- **Maintenance Triage** — Analyzes maintenance patterns, prioritizes requests, suggests preventive actions

Each agent uses the think-act-observe loop with access to 10 property intelligence tools.

## LLM Providers

REMI supports multiple LLM providers (install as extras):

```bash
uv pip install -e ".[openai]"      # OpenAI
uv pip install -e ".[anthropic]"   # Anthropic
uv pip install -e ".[gemini]"      # Google Gemini
uv pip install -e ".[all-providers]"
```

## Development

```bash
# Run tests
python -m pytest tests/ -v

# Run with coverage
python -m pytest tests/ --cov=remi

# Lint
ruff check src/ tests/

# Type check
mypy src/
```
