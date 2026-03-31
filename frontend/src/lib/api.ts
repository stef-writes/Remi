import type {
  ActionItemResponse,
  AgentMeta,
  EntityNoteResponse,
  ModelsConfig,
  ManagerListItem,
  ManagerNoteResponse,
  ManagerReview,
  PortfolioOverview,
  DelinquencyBoard,
  LeaseCalendar,
  VacancyTracker,
  NeedsManagerResponse,
  PropertyDetail,
  RentRollResponse,
  DocumentMeta,
  SnapshotHistory,
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

  dashboardOverview: (managerId?: string) =>
    get<PortfolioOverview>(`/api/v1/dashboard/overview${qs({ manager_id: managerId })}`),

  delinquencyBoard: (managerId?: string) =>
    get<DelinquencyBoard>(`/api/v1/dashboard/delinquency${qs({ manager_id: managerId })}`),

  leasesExpiring: (days = 90, managerId?: string) =>
    get<LeaseCalendar>(`/api/v1/dashboard/leases/expiring${qs({ days, manager_id: managerId })}`),

  vacancyTracker: (managerId?: string) =>
    get<VacancyTracker>(`/api/v1/dashboard/vacancies${qs({ manager_id: managerId })}`),

  needsManager: () =>
    get<NeedsManagerResponse>("/api/v1/dashboard/needs-manager"),

  snapshots: (managerId?: string) =>
    get<SnapshotHistory>(`/api/v1/dashboard/snapshots${qs({ manager_id: managerId })}`),

  // --- Managers ---

  listManagers: () =>
    get<{ managers: ManagerListItem[] }>("/api/v1/managers").then((r) => r.managers),

  getManagerReview: (id: string) =>
    get<ManagerReview>(`/api/v1/managers/${id}/review`),

  // --- Properties ---

  listProperties: (portfolioId?: string) =>
    get<{ properties: PropertyDetail[] }>(
      `/api/v1/properties${qs({ portfolio_id: portfolioId })}`
    ).then((r) => r.properties),

  getProperty: (id: string) => get<PropertyDetail>(`/api/v1/properties/${id}`),

  getRentRoll: (propertyId: string) =>
    get<RentRollResponse>(`/api/v1/properties/${propertyId}/rent-roll`),

  // --- Documents ---

  listDocuments: () =>
    get<{ documents: DocumentMeta[] }>("/api/v1/documents").then((r) => r.documents),

  getDocument: (id: string) =>
    get<DocumentMeta & { preview: Record<string, unknown>[] }>(`/api/v1/documents/${id}`),

  queryRows: (id: string, limit = 100) =>
    get<{ rows: Record<string, unknown>[]; count: number }>(
      `/api/v1/documents/${id}/rows?limit=${limit}`
    ),

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
    return res.json() as Promise<{
      id: string;
      filename: string;
      row_count: number;
      report_type: string;
      columns: string[];
      knowledge: { entities_extracted: number; relationships_extracted: number; ambiguous_rows: number };
    }>;
  },

  deleteDocument: (id: string) =>
    fetch(`${BASE}/api/v1/documents/${id}`, { method: "DELETE" }).then((r) => r.json()),

  // --- Agents ---

  listAgents: () =>
    get<{ agents: AgentMeta[] }>("/api/v1/agents").then((r) => r.agents),

  listModels: () =>
    get<ModelsConfig>("/api/v1/agents/models"),

  autoAssign: async () => {
    const res = await fetch(`${BASE}/api/v1/dashboard/auto-assign`, { method: "POST" });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || res.statusText);
    }
    return res.json() as Promise<{ assigned: number; unresolved: number; message: string }>;
  },

  assignProperties: async (managerId: string, propertyIds: string[]) => {
    const res = await fetch(`${BASE}/api/v1/managers/${managerId}/assign`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ property_ids: propertyIds }),
    });
    if (!res.ok) {
      const data = await res.json().catch(() => ({}));
      throw new Error(data.detail || res.statusText);
    }
    return res.json() as Promise<{ manager_id: string; assigned: number; already_assigned: number; not_found: string[] }>;
  },

  // --- Manager CRUD ---

  updateManager: async (managerId: string, updates: { name?: string; email?: string; company?: string; phone?: string }) => {
    const res = await fetch(`${BASE}/api/v1/managers/${managerId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ manager_id: string; portfolio_id: string; name: string }>;
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

  updateProperty: async (propertyId: string, updates: { name?: string; portfolio_id?: string; street?: string; city?: string; state?: string; zip_code?: string }) => {
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

  // --- Tenant CRUD ---

  getTenant: (tenantId: string) =>
    get<{ tenant_id: string; name: string; leases: unknown[] }>(`/api/v1/tenants/${tenantId}`),

  updateTenant: async (tenantId: string, updates: { email?: string; phone?: string }) => {
    const res = await fetch(`${BASE}/api/v1/tenants/${tenantId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(updates),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ id: string; name: string }>;
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

  // --- Manager Notes ---

  listManagerNotes: (managerId: string) =>
    get<{ notes: ManagerNoteResponse[]; total: number }>(`/api/v1/actions/notes${qs({ manager_id: managerId })}`),

  createManagerNote: async (managerId: string, content: string) => {
    const res = await fetch(`${BASE}/api/v1/actions/notes`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ manager_id: managerId, content }),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<ManagerNoteResponse>;
  },

  updateManagerNote: async (noteId: string, content: string) => {
    const res = await fetch(`${BASE}/api/v1/actions/notes/${noteId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content }),
    });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<ManagerNoteResponse>;
  },

  deleteManagerNote: async (noteId: string) => {
    const res = await fetch(`${BASE}/api/v1/actions/notes/${noteId}`, { method: "DELETE" });
    if (!res.ok) { const d = await res.json().catch(() => ({})); throw new Error(d.detail || res.statusText); }
    return res.json() as Promise<{ deleted: boolean }>;
  },

  // --- Entity Notes (KnowledgeGraph-backed) ---

  listEntityNotes: (entityType: string, entityId: string) =>
    get<{ notes: EntityNoteResponse[]; total: number }>(`/api/v1/notes?entity_type=${encodeURIComponent(entityType)}&entity_id=${encodeURIComponent(entityId)}`),

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
};
