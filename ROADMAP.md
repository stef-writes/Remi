# REMI Roadmap

## Current State

REMI operates as a director-level intelligence tool. The director (or admin)
uploads AppFolio report exports manually, REMI ingests them into the knowledge
graph, runs the entailment engine to produce signals, and provides an AI agent
for investigation and analysis. One role, one portal, manual ingestion.

---

## Phase: RBAC & Property Manager Portal

**Prerequisite for email triage.** Before REMI can route tenant requests to
individual property managers, managers need their own accounts and views.

- **Role-based access control** — Director, PropertyManager, (eventually Tenant)
- **Manager portal** — a PM sees only their portfolio: their properties, their
  signals, their maintenance queue, their tenant communications
- **Director retains admin-level view** — cross-portfolio, cross-manager oversight

This phase defines the routing targets that the email triage system needs.

---

## Phase: REMI Email — AI-Owned Mailbox

REMI gets its own email address (`remi@yourcompany.com`) — not as a narrow
integration, but as an employee-grade mailbox. One address, one inbound
endpoint, a classifier that grows over time. The infrastructure is built once;
capabilities are added incrementally.

### Why one mailbox, not special-purpose addresses

Setting up email infrastructure (DNS, MX records, inbound webhooks, sender
identity) is the same work whether it serves one use case or ten. A single
`remi@` address that classifies and routes internally means:

- One DNS setup, one webhook, one auth config
- New capabilities = new classifier categories + handlers, not new infrastructure
- People (tenants, managers, vendors) learn one address
- REMI accumulates a unified communication history in the knowledge graph

### Architecture

```
remi@yourcompany.com
       │
       ▼
  /api/v1/email/inbound  (webhook from SendGrid / Mailgun / SES)
       │
       ▼
  EmailService.classify()  (LLM-backed, domain.yaml rules as context)
       │
       ├── appfolio_report    → extract attachment → DocumentIngestService.ingest_upload()
       ├── tenant_maintenance → resolve tenant → create MaintenanceRequest → triage
       ├── tenant_inquiry     → resolve tenant → log → draft response for PM review
       ├── manager_forward    → ingest as context → link to entities
       ├── director_query     → route to director agent (email as chat transport)
       └── unknown            → log + notify admin + learn
```

Every inbound email becomes an `EmailMessage` entity in the knowledge graph,
linked to the sender (Tenant, PropertyManager, or unknown), the relevant
property/unit, and any entities it creates (maintenance requests, etc.). The
entailment engine sees these. Signals reflect them. The director agent can
query them.

### Capability 1: Automated Report Ingestion (Director / Admin Level)

**Does not require RBAC.** This is the first capability to build because it
plugs directly into the existing pipeline at the current access level.

AppFolio supports scheduled email reports — Rent Roll, Delinquency, Lease
Expiration, Property Directory — sent as CSV/Excel attachments on a daily or
weekly cadence.

**What it replaces:** Alex manually downloading reports from AppFolio and
uploading them through the REMI dashboard.

**How it works:**
1. Configure AppFolio to email scheduled reports to `remi@yourcompany.com`
2. The inbound webhook receives the email
3. Classifier detects AppFolio report (sender domain + attachment presence)
4. Extracts CSV/Excel attachment
5. Calls `DocumentIngestService.ingest_upload()` — the exact same pipeline
   that runs today on manual upload
6. `detect_report_type()` fingerprints the columns, `IngestionService` creates
   entities, signal pipeline runs, pattern detection runs, embeddings update

The entire existing ingestion pipeline is reused. The new code is:
- One webhook router (`/api/v1/email/inbound`)
- One email parsing adapter (extract sender, subject, attachments from webhook payload)
- One classifier rule (AppFolio sender domain + has attachment = report)
- Settings for webhook auth + allowed sender domains

**Result:** Knowledge graph stays current automatically. No human in the loop
for routine data ingestion.

### Capability 2: Tenant Maintenance Triage (Requires RBAC + PM Portal)

**Requires RBAC** so that triaged requests can be routed to the correct
property manager's queue.

Tenants email `remi@yourcompany.com` with maintenance requests. REMI:

1. **Resolves the tenant** — matches sender email to `Tenant.email` in
   PropertyStore, identifies unit, property, and assigned manager
2. **Classifies the request** — LLM extracts: issue category (plumbing,
   electrical, HVAC, pest, structural, cosmetic), urgency, affected area,
   description
3. **Creates a MaintenanceRequest entity** in the knowledge graph, linked to
   tenant → unit → property → manager
4. **Triages by urgency** — domain.yaml rules define emergency vs. high vs.
   normal vs. low based on keywords and categories
5. **Routes to the property manager** — appears in their PM portal queue,
   with urgency and classification pre-filled
6. **Acknowledges receipt** — auto-reply to the tenant confirming REMI received
   their request (configurable templates)
7. **Signal pipeline runs** — the new request may trigger or strengthen a
   `MaintenanceBacklog` signal for that manager

**Domain rules (in domain.yaml):**

```yaml
email_categories:
  tenant_maintenance:
    urgency_keywords:
      emergency: [flood, fire, no heat, gas smell, sewage, no water, carbon monoxide]
      high: [leak, broken lock, no hot water, mold, electrical spark]
      normal: [repair, fix, replace, squeaky, paint, clogged]
      low: [cosmetic, scratch, suggestion, request]
```

**Result:** Tenants get fast acknowledgment. Managers get pre-triaged requests
in their portal. The director sees maintenance patterns across the portfolio
through signals. Nobody manually categorizes or routes emails.

### Capability 3: General Tenant Communication (Requires RBAC + PM Portal)

Tenant emails that aren't maintenance — rent questions, lease inquiries,
move-out notices, complaints:

1. Resolve tenant, classify intent
2. Log as `TenantCommunication` entity in knowledge graph
3. Draft a response using the LLM (grounded in lease terms, payment history,
   property policies from the knowledge graph)
4. Route draft to property manager for review/approval/edit before sending
5. Over time, confidence-gated auto-response for routine items

### Capability 4: Manager and Director Communication

- **Manager forwards to REMI** — CC `remi@` on a conversation. The email
  becomes an observation in the knowledge graph. The `CommunicationGap` signal
  weakens because the manager *is* communicating.
- **Director emails REMI a question** — "Pull together vacancy trends for
  Marcus's portfolio this quarter." This is a chat message arriving via email
  transport — same `director` agent, different input channel.

### Capability 5: Confidence-Gated Auto-Response

The same graduated trust model used in the hypothesis pipeline
(`PROPOSED → CONFIRMED → graduated`):

- Start with all responses requiring PM approval
- Track approval rate per category — if PMs approve 95% of maintenance
  acknowledgments unedited, propose auto-send for that category
- Director confirms the auto-response policy
- REMI handles routine communications independently, PMs handle exceptions

---

## Email Entity Model

```
EmailMessage
  properties: sender, recipient, subject, body_text, received_at,
              category, status, direction (inbound/outbound)
  links:
    FROM_TENANT → Tenant          (resolved by sender email)
    FROM_MANAGER → PropertyManager (resolved by sender email)
    REGARDING_UNIT → Unit          (extracted from content)
    REGARDING_PROPERTY → Property
    MANAGED_BY → PropertyManager
    CREATED_REQUEST → MaintenanceRequest
    IN_REPLY_TO → EmailMessage     (threading)
```

---

## Infrastructure (One-Time Setup)

Regardless of which capabilities are active, the infrastructure is:

1. **DNS** — MX record for `remi@yourcompany.com` pointing to the email
   provider (SendGrid, Mailgun, or AWS SES)
2. **Inbound webhook** — provider parses email and POSTs to REMI's endpoint
3. **Outbound sending** — same provider, configured with SPF/DKIM/DMARC so
   replies come from `remi@yourcompany.com`
4. **Webhook authentication** — verify inbound requests are genuinely from the
   email provider (signed payloads)
5. **Settings** — `EmailSettings` added to `RemiSettings`: provider config,
   webhook auth token, allowed sender domains, REMI's sending address

---

## Dependency Chain

```
Current state (director-only, manual upload)
    │
    ├── Email Capability 1: Report Ingestion ← can build now
    │     (no new roles needed, plugs into existing pipeline)
    │
    ▼
RBAC + Property Manager Portal
    │
    ├── Email Capability 2: Maintenance Triage ← needs PM routing target
    ├── Email Capability 3: Tenant Communication ← needs PM approval queue
    ├── Email Capability 4: Manager/Director Email ← needs role resolution
    │
    ▼
Email Capability 5: Auto-Response ← needs trust data from Capabilities 2-4
```

---

*Document date: 2026-03-31*
