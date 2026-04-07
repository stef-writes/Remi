import type {
  ActionItemResponse,
  ChangeSetSummary,
  CorrectRowResponse,
  DashboardOverview,
  DelinquencyTrend,
  EntityNoteResponse,
  ModelsConfig,
  ManagerListItem,
  ManagerReview,
  MeetingBriefResponse,
  MeetingBriefListResponse,
  DelinquencyBoard,
  LeaseCalendar,
  LeaseListResponse,
  OccupancyTrend,
  RentTrend,
  VacancyTracker,
  NeedsManagerResponse,
  PropertyDetail,
  RentRollResponse,
  MaintenanceListResponse,
  MaintenanceSummary,
  MaintenanceTrend,
  DocumentMeta,
  SearchResponse,
  SignalSummary,
  UploadResult,
  GraphSnapshot,
  GraphSubgraph,
  OperationalGraph,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || res.statusText);
  }
  return res.json();
}

function qs(params: Record<string, string | number | undefined | null>): string {
  const entries = Object.entries(params).filter(([, v]) => v != null && v !== "");
  if (!entries.length) return "";
  return "?" + new URLSearchParams(entries.map(([k, v]) => [k, String(v)])).toString();
}

export const api = {
  // --- Dashboard ---

  dashboardOverview: (scope?: { manager_id?: string; owner_id?: string }) =>
    get<DashboardOverview>(`/api/v1/dashboard/overview${qs(scope || {})}`),

  delinquencyBoard: (scope?: { manager_id?: string; owner_id?: string }) =>
    get<DelinquencyBoard>(`/api/v1/dashboard/delinquency${qs(scope || {})}`),

  leasesExpiring: (days = 90, scope?: { manager_id?: string; owner_id?: string }) =>
    get<LeaseCalendar>(`/api/v1/dashboard/leases/expiring${qs({ days, ...scope })}`),

  vacancyTracker: (scope?: { manager_id?: string; owner_id?: string }) =>
    get<VacancyTracker>(`/api/v1/dashboard/vacancies${qs(scope || {})}`),

  needsManager: () =>
    get<NeedsManagerResponse>("/api/v1/dashboard/needs-manager"),

  // --- Trends ---

  delinquencyTrend: (scope?: { manager_id?: string; property_id?: string; periods?: number }) =>
    get<DelinquencyTrend>(`/api/v1/dashboard/trends/delinquency${qs(scope || {})}`),

  occupancyTrend: (scope?: { manager_id?: string; property_id?: string; periods?: number }) =>
    get<OccupancyTrend>(`/api/v1/dashboard/trends/occupancy${qs(scope || {})}`),

  rentTrend: (scope?: { manager_id?: string; property_id?: string; periods?: number }) =>
    get<RentTrend>(`/api/v1/dashboard/trends/rent${qs(scope || {})}`),

  maintenanceTrend: (scope?: { manager_id?: string; property_id?: string; unit_id?: string; periods?: number }) =>
    get<MaintenanceTrend>(`/api/v1/dashboard/trends/maintenance${qs(scope || {})}`),

  // --- Owners ---

  listOwners: () =>
    get<{ id: string; name: string; owner_type: string; company: string | null; email: string; phone: string | null; property_count: number }[]>("/api/v1/owners"),

  // --- Search ---

  search: (q: string, limit = 10) =>
    get<SearchResponse>(`/api/v1/search${qs({ q, limit })}`),

  // --- Managers ---

  listManagers: () =>
    get<{ managers: (Omit<ManagerListItem, "id"> & { manager_id: string })[] }>("/api/v1/managers")
      .then((r) => r.managers.map(({ manager_id, ...rest }) => ({ id: manager_id, ...rest }))),

  getManagerReview: (id: string) =>
    get<ManagerReview>(`/api/v1/managers/${id}/review`),

  generateMeetingBrief: async (managerId: string, focus?: string) => {
    const res = await fetch(`${BASE}/api/v1/managers/${managerId}/meeting-brief`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ focus: focus || null }),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<MeetingBriefResponse>;
  },

  listMeetingBriefs: (managerId: string, limit = 10) =>
    get<MeetingBriefListResponse>(`/api/v1/managers/${managerId}/meeting-briefs?limit=${limit}`),

  // --- Properties ---

  listProperties: (params?: { manager_id?: string; owner_id?: string }) =>
    get<{ properties: PropertyDetail[] }>(`/api/v1/properties${qs(params || {})}`).then((r) => r.properties),

  getProperty: (id: string) => get<PropertyDetail>(`/api/v1/properties/${id}`),

  getRentRoll: (propertyId: string) =>
    get<RentRollResponse>(`/api/v1/properties/${propertyId}/rent-roll`),

  assignProperties: async (managerId: string, propertyIds: string[]) => {
    const res = await fetch(`${BASE}/api/v1/managers/${managerId}/assign`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ property_ids: propertyIds }),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ manager_id: string; assigned: number; already_assigned: number; not_found: string[] }>;
  },

  // --- Leases ---

  listLeases: (params?: { property_id?: string; status?: string }) =>
    get<LeaseListResponse>(`/api/v1/leases${qs(params || {})}`),

  // --- Maintenance ---

  listMaintenance: (params?: { property_id?: string; unit_id?: string; status?: string }) =>
    get<MaintenanceListResponse>(`/api/v1/maintenance${qs(params || {})}`),

  maintenanceSummary: (params?: { property_id?: string; unit_id?: string }) =>
    get<MaintenanceSummary>(`/api/v1/maintenance/summary${qs(params || {})}`),

  // --- Documents / Knowledge Base ---

  listDocuments: (params?: { q?: string; kind?: string; tags?: string; sort?: string; limit?: number }) =>
    get<{ documents: DocumentMeta[] }>(
      `/api/v1/documents${qs(params || {})}`
    ).then((r) => r.documents),

  getDocument: (id: string) =>
    get<DocumentMeta & { preview: Record<string, unknown>[] }>(`/api/v1/documents/${id}`),

  queryRows: (id: string, limit = 100) =>
    get<{ rows: Record<string, unknown>[]; count: number }>(
      `/api/v1/documents/${id}/rows?limit=${limit}`
    ),

  queryChunks: (id: string, limit = 100) =>
    get<{ document_id: string; chunks: { index: number; text: string; page: number | null }[]; count: number }>(
      `/api/v1/documents/${id}/chunks?limit=${limit}`
    ),

  listDocumentTags: () =>
    get<{ tags: string[] }>("/api/v1/documents/tags").then((r) => r.tags),

  updateDocumentTags: async (id: string, tags: string[]) => {
    const res = await fetch(`${BASE}/api/v1/documents/${id}/tags`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tags }),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ tags: string[] }>;
  },

  uploadDocument: async (file: File, manager?: string) => {
    const form = new FormData();
    form.append("file", file);
    if (manager) form.append("manager", manager);
    const res = await fetch(`${BASE}/api/v1/documents/upload`, {
      method: "POST",
      body: form,
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || res.statusText);
    }
    return res.json() as Promise<UploadResult>;
  },

  deleteDocument: (id: string) =>
    fetch(`${BASE}/api/v1/documents/${id}`, { method: "DELETE" }).then((r) => r.json()),

  correctRow: async (documentId: string, rowData: Record<string, unknown>, reportType?: string) => {
    const res = await fetch(`${BASE}/api/v1/documents/${documentId}/correct-row`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ row_data: rowData, report_type: reportType }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || res.statusText);
    }
    return res.json() as Promise<CorrectRowResponse>;
  },

  correctEntity: async (entityType: string, entityId: string, corrections: Record<string, unknown>) => {
    const res = await fetch(`${BASE}/api/v1/knowledge/correct`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entity_type: entityType, entity_id: entityId, corrections }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || res.statusText);
    }
    return res.json() as Promise<Record<string, unknown>>;
  },

  // --- Agents ---

  listModels: () =>
    get<ModelsConfig>("/api/v1/agents/models"),

  // --- Manager CRUD ---

  createManager: async (data: { name: string; email?: string; company?: string; phone?: string }) => {
    const res = await fetch(`${BASE}/api/v1/managers`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ manager_id: string; name: string }>;
  },

  updateManager: async (managerId: string, updates: { name?: string; email?: string; company?: string; phone?: string }) => {
    const res = await fetch(`${BASE}/api/v1/managers/${managerId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ manager_id: string; name: string }>;
  },

  deleteManager: async (managerId: string) => {
    const res = await fetch(`${BASE}/api/v1/managers/${managerId}`, { method: "DELETE" });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ deleted: boolean }>;
  },

  mergeManagers: async (sourceId: string, targetId: string) => {
    const res = await fetch(`${BASE}/api/v1/managers/merge`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_manager_id: sourceId, target_manager_id: targetId }),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ target_manager_id: string; properties_moved: number; source_deleted: boolean }>;
  },

  // --- Property CRUD ---

  createProperty: async (data: { name: string; manager_id?: string; owner_id?: string; street: string; city: string; state: string; zip_code: string; property_type?: string; year_built?: number }) => {
    const res = await fetch(`${BASE}/api/v1/properties`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ property_id: string; name: string }>;
  },

  updateProperty: async (propertyId: string, updates: { name?: string; street?: string; city?: string; state?: string; zip_code?: string; manager_id?: string; owner_id?: string }) => {
    const res = await fetch(`${BASE}/api/v1/properties/${propertyId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ id: string; name: string }>;
  },

  deleteProperty: async (propertyId: string) => {
    const res = await fetch(`${BASE}/api/v1/properties/${propertyId}`, { method: "DELETE" });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ deleted: boolean }>;
  },

  // --- Lease CRUD ---

  createLease: async (data: { unit_id: string; tenant_id: string; property_id: string; start_date: string; end_date: string; monthly_rent: number; deposit?: number; status?: string }) => {
    const res = await fetch(`${BASE}/api/v1/leases`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ lease_id: string; unit_id: string; tenant_id: string; property_id: string }>;
  },

  updateLease: async (leaseId: string, updates: { monthly_rent?: number; status?: string; end_date?: string; renewal_status?: string; is_month_to_month?: boolean }) => {
    const res = await fetch(`${BASE}/api/v1/leases/${leaseId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ id: string; name: string }>;
  },

  deleteLease: async (leaseId: string) => {
    const res = await fetch(`${BASE}/api/v1/leases/${leaseId}`, { method: "DELETE" });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ deleted: boolean }>;
  },

  // --- Tenant CRUD ---

  createTenant: async (data: { name: string; email?: string; phone?: string }) => {
    const res = await fetch(`${BASE}/api/v1/tenants`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ tenant_id: string; name: string }>;
  },

  updateTenant: async (tenantId: string, updates: { name?: string; email?: string; phone?: string; status?: string }) => {
    const res = await fetch(`${BASE}/api/v1/tenants/${tenantId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ id: string; name: string }>;
  },

  deleteTenant: async (tenantId: string) => {
    const res = await fetch(`${BASE}/api/v1/tenants/${tenantId}`, { method: "DELETE" });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ deleted: boolean }>;
  },

  // --- Maintenance CRUD ---

  createMaintenance: async (data: { unit_id: string; property_id: string; title: string; description?: string; category?: string; priority?: string }) => {
    const res = await fetch(`${BASE}/api/v1/maintenance`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ request_id: string; title: string; property_id: string; unit_id: string }>;
  },

  updateMaintenance: async (requestId: string, updates: { title?: string; description?: string; status?: string; priority?: string; category?: string; vendor?: string; cost?: number }) => {
    const res = await fetch(`${BASE}/api/v1/maintenance/${requestId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ id: string; name: string }>;
  },

  deleteMaintenance: async (requestId: string) => {
    const res = await fetch(`${BASE}/api/v1/maintenance/${requestId}`, { method: "DELETE" });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ deleted: boolean }>;
  },

  // --- Action Items ---

  listActionItems: (params?: { manager_id?: string; property_id?: string; status?: string }) =>
    get<{ items: ActionItemResponse[]; total: number }>(`/api/v1/actions/items${qs(params || {})}`),

  createActionItem: async (data: { title: string; description?: string; priority?: string; manager_id?: string; property_id?: string; tenant_id?: string; due_date?: string }) => {
    const res = await fetch(`${BASE}/api/v1/actions/items`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<ActionItemResponse>;
  },

  updateActionItem: async (itemId: string, updates: { title?: string; description?: string; status?: string; priority?: string; due_date?: string }) => {
    const res = await fetch(`${BASE}/api/v1/actions/items/${itemId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<ActionItemResponse>;
  },

  deleteActionItem: async (itemId: string) => {
    const res = await fetch(`${BASE}/api/v1/actions/items/${itemId}`, { method: "DELETE" });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ deleted: boolean }>;
  },

  // --- Entity Notes ---

  listEntityNotes: (entityType: string, entityId: string) =>
    get<{ notes: EntityNoteResponse[]; total: number }>(`/api/v1/notes?entity_type=${encodeURIComponent(entityType)}&entity_id=${encodeURIComponent(entityId)}`),

  batchEntityNotes: async (entityType: string, entityIds: string[]) => {
    const res = await fetch(`${BASE}/api/v1/notes/batch`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ entity_type: entityType, entity_ids: entityIds }),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ notes_by_entity: Record<string, EntityNoteResponse[]> }>;
  },

  createEntityNote: async (entityType: string, entityId: string, content: string) => {
    const res = await fetch(`${BASE}/api/v1/notes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, entity_type: entityType, entity_id: entityId }),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<EntityNoteResponse>;
  },

  updateEntityNote: async (noteId: string, content: string) => {
    const res = await fetch(`${BASE}/api/v1/notes/${noteId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<EntityNoteResponse>;
  },

  deleteEntityNote: async (noteId: string) => {
    const res = await fetch(`${BASE}/api/v1/notes/${noteId}`, { method: "DELETE" });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ deleted: boolean }>;
  },

  // --- Ontology / Graph Visualization ---

  graphSnapshot: (scope?: { manager_id?: string; owner_id?: string }) =>
    get<GraphSnapshot>(`/api/v1/ontology/snapshot${qs(scope || {})}`),

  graphSubgraph: (entityId: string, depth = 2) =>
    get<GraphSubgraph>(`/api/v1/ontology/subgraph/${entityId}${qs({ depth })}`),

  operationalGraph: () =>
    get<OperationalGraph>("/api/v1/ontology/graph/operational"),

  // --- Signals ---

  listSignals: (params?: { manager_id?: string; property_id?: string; severity?: string; signal_type?: string }) =>
    get<{ count: number; signals: SignalSummary[] }>(`/api/v1/signals${qs(params || {})}`),

  // --- Events / Audit Trail ---

  listEvents: (limit = 20) =>
    get<{ count: number; changesets: ChangeSetSummary[] }>(`/api/v1/events${qs({ limit })}`),

  entityEvents: (entityId: string, limit = 50) =>
    get<{ entity_id: string; count: number; changesets: ChangeSetSummary[] }>(
      `/api/v1/events/entity/${entityId}${qs({ limit })}`,
    ),

};
