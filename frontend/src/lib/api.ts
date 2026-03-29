import type {
  ManagerListItem,
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
};
