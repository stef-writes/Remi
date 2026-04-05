// --- Property Managers (director-level) ---

export interface ManagerListItem {
  id: string;
  name: string;
  email: string;
  company: string | null;
  portfolio_count: number;
  property_count: number;
  total_units: number;
  occupied: number;
  vacant: number;
  occupancy_rate: number;
  total_actual_rent: number;
  total_loss_to_lease: number;
  total_vacancy_loss: number;
  open_maintenance: number;
  emergency_maintenance: number;
  expiring_leases_90d: number;
  expired_leases: number;
  below_market_units: number;
  delinquent_count: number;
  total_delinquent_balance: number;
}

export interface ManagerPropertySummary {
  property_id: string;
  property_name: string;
  portfolio_id: string;
  portfolio_name: string;
  total_units: number;
  occupied: number;
  vacant: number;
  occupancy_rate: number;
  monthly_actual: number;
  monthly_market: number;
  loss_to_lease: number;
  vacancy_loss: number;
  open_maintenance: number;
  emergency_maintenance: number;
  expiring_leases: number;
  expired_leases: number;
  below_market_units: number;
  issue_count: number;
}

export interface ManagerUnitIssue {
  property_id: string;
  property_name: string;
  unit_id: string;
  unit_number: string;
  issues: string[];
  monthly_impact: number;
}

export interface ManagerReview {
  manager_id: string;
  name: string;
  email: string;
  company: string | null;
  portfolio_count: number;
  property_count: number;
  total_units: number;
  occupied: number;
  vacant: number;
  occupancy_rate: number;
  total_market_rent: number;
  total_actual_rent: number;
  total_loss_to_lease: number;
  total_vacancy_loss: number;
  open_maintenance: number;
  emergency_maintenance: number;
  expiring_leases_90d: number;
  expired_leases: number;
  below_market_units: number;
  delinquent_count: number;
  total_delinquent_balance: number;
  properties: ManagerPropertySummary[];
  top_issues: ManagerUnitIssue[];
}

// --- Dashboard Overview ---

export interface ManagerOverview {
  manager_id: string;
  manager_name: string;
  portfolio_count: number;
  property_count: number;
  total_units: number;
  occupied: number;
  vacant: number;
  occupancy_rate: number;
  total_monthly_rent: number;
  total_market_rent: number;
  loss_to_lease: number;
}

export interface PortfolioOverview {
  total_managers: number;
  total_portfolios: number;
  total_properties: number;
  total_units: number;
  occupied: number;
  vacant: number;
  occupancy_rate: number;
  total_monthly_rent: number;
  total_market_rent: number;
  total_loss_to_lease: number;
  managers: ManagerOverview[];
}

// --- Delinquency ---

export interface DelinquentTenant {
  tenant_id: string;
  tenant_name: string;
  status: string;
  property_id: string | null;
  property_name: string;
  unit_id: string | null;
  unit_number: string;
  balance_owed: number;
  balance_0_30: number;
  balance_30_plus: number;
  last_payment_date: string | null;
  tags: string[];
  delinquency_notes: string | null;
}

export interface DelinquencyBoard {
  total_delinquent: number;
  total_balance: number;
  tenants: DelinquentTenant[];
}

// --- Leases ---

export interface ExpiringLease {
  lease_id: string;
  tenant_name: string;
  property_id: string;
  property_name: string;
  unit_id: string;
  unit_number: string;
  monthly_rent: number;
  market_rent: number;
  end_date: string;
  days_left: number;
  is_month_to_month: boolean;
}

export interface LeaseCalendar {
  days_window: number;
  total_expiring: number;
  month_to_month_count: number;
  leases: ExpiringLease[];
}

// --- Vacancies ---

export interface VacantUnit {
  unit_id: string;
  unit_number: string;
  property_id: string;
  property_name: string;
  occupancy_status: string | null;
  days_vacant: number | null;
  market_rent: number;
  listed_on_website: boolean;
  listed_on_internet: boolean;
}

export interface VacancyTracker {
  total_vacant: number;
  total_notice: number;
  total_market_rent_at_risk: number;
  avg_days_vacant: number | null;
  units: VacantUnit[];
}

// --- Needs Manager ---

export interface NeedsManagerProperty {
  id: string;
  name: string;
  address: string;
}

export interface NeedsManagerResponse {
  total: number;
  properties: NeedsManagerProperty[];
}

// --- Portfolio & Property ---

export interface PortfolioSummary {
  portfolio_id: string;
  name: string;
  manager: string;
  total_properties: number;
  total_units: number;
  occupied_units: number;
  occupancy_rate: number;
  monthly_revenue: number;
  properties: PropertyOverview[];
}

export interface PortfolioListItem {
  id: string;
  name: string;
  manager: string;
  property_count: number;
  description: string;
}

export interface PropertyOverview {
  id: string;
  name: string;
  type: string;
  total_units: number;
  occupied: number;
  monthly_revenue: number;
}

export interface PropertyDetail {
  id: string;
  name: string;
  address: Record<string, string>;
  property_type: string;
  year_built: number;
  portfolio_id: string | null;
  portfolio_name: string | null;
  manager_id: string | null;
  manager_name: string | null;
  total_units: number;
  units: Unit[];
  occupancy_rate: number;
  monthly_revenue: number;
  active_leases: number;
}

export interface Unit {
  id: string;
  property_id: string;
  unit_number: string;
  bedrooms: number;
  bathrooms: number;
  sqft: number;
  market_rent: number;
  current_rent: number;
  status: "vacant" | "occupied" | "maintenance" | "offline";
  floor: number;
}

// --- Rent Roll (joined view per unit) ---

export interface RentRollLease {
  id: string;
  status: "active" | "expired" | "terminated" | "pending";
  start_date: string;
  end_date: string;
  monthly_rent: number;
  deposit: number;
  days_to_expiry: number | null;
}

export interface RentRollTenant {
  id: string;
  name: string;
  email: string;
  phone: string | null;
}

export interface RentRollMaintenance {
  id: string;
  title: string;
  category: string;
  priority: "low" | "medium" | "high" | "emergency";
  status: "open" | "in_progress";
  cost: number | null;
}

export type UnitIssue =
  | "vacant"
  | "down_for_maintenance"
  | "below_market"
  | "expired_lease"
  | "expiring_soon"
  | "open_maintenance";

export interface RentRollRow {
  unit_id: string;
  unit_number: string;
  floor: number | null;
  bedrooms: number | null;
  bathrooms: number | null;
  sqft: number | null;
  status: "vacant" | "occupied" | "maintenance" | "offline";
  market_rent: number;
  current_rent: number;
  rent_gap: number;
  pct_below_market: number;
  lease: RentRollLease | null;
  tenant: RentRollTenant | null;
  open_maintenance: number;
  maintenance_items: RentRollMaintenance[];
  issues: UnitIssue[];
}

export interface RentRollResponse {
  property_id: string;
  property_name: string;
  total_units: number;
  occupied: number;
  vacant: number;
  total_market_rent: number;
  total_actual_rent: number;
  total_loss_to_lease: number;
  total_vacancy_loss: number;
  rows: RentRollRow[];
}

// --- Leases (list) ---

export interface LeaseListItem {
  id: string;
  tenant: string;
  unit_id: string;
  property_id: string;
  start: string;
  end: string;
  rent: number;
  status: string;
}

export interface LeaseListResponse {
  count: number;
  leases: LeaseListItem[];
}

// --- Maintenance ---

export interface MaintenanceRequest {
  id: string;
  property_id: string;
  unit_id: string;
  title: string;
  category: string;
  priority: "low" | "medium" | "high" | "emergency";
  status: "open" | "in_progress" | "completed" | "cancelled";
  cost: number | null;
  created: string;
  resolved: string | null;
}

export interface MaintenanceListResponse {
  count: number;
  requests: MaintenanceRequest[];
}

export interface MaintenanceSummary {
  total: number;
  by_status: Record<string, number>;
  by_category: Record<string, number>;
  total_cost: number;
}

// --- Documents / Knowledge Base ---

export type DocumentKind = "tabular" | "text" | "image";

export interface TextChunk {
  index: number;
  text: string;
  page: number | null;
}

export interface DocumentMeta {
  id: string;
  filename: string;
  content_type: string;
  kind: DocumentKind;
  row_count: number;
  columns: string[];
  report_type: string;
  chunk_count: number;
  page_count: number;
  tags: string[];
  size_bytes: number;
  uploaded_at: string;
}

export type ReviewKind =
  | "ambiguous_row"
  | "validation_warning"
  | "entity_match"
  | "classification_uncertain"
  | "manager_inferred";

export type ReviewSeverity = "info" | "warning" | "action_needed";

export interface ReviewOption {
  id: string;
  label: string;
}

export interface ReviewItem {
  kind: ReviewKind;
  severity: ReviewSeverity;
  message: string;
  row_index?: number | null;
  entity_type?: string | null;
  entity_id?: string | null;
  field_name?: string | null;
  raw_value?: string | null;
  suggestion?: string | null;
  options?: ReviewOption[];
  row_data?: Record<string, unknown> | null;
}

export interface UploadKnowledge {
  entities_extracted: number;
  relationships_extracted: number;
  ambiguous_rows: number;
  rows_accepted: number;
  rows_rejected: number;
  rows_skipped: number;
  validation_warnings: string[];
  review_items: ReviewItem[];
}

export interface UploadResult {
  id: string;
  filename: string;
  kind: string;
  row_count: number;
  report_type: string;
  columns: string[];
  chunk_count: number;
  page_count: number;
  tags: string[];
  size_bytes: number;
  knowledge: UploadKnowledge;
}

export interface CorrectRowResponse {
  accepted: boolean;
  entities_created: number;
  relationships_created: number;
  review_items: ReviewItem[];
  validation_warnings: string[];
}

// --- Chat ---

export interface UsageInfo {
  prompt_tokens: number;
  completion_tokens: number;
  total_tokens: number;
  model?: string;
  provider?: string;
  cost?: number;
  latency_ms?: number;
  trace_id?: string;
  intent?: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: number;
  tools?: ToolCall[];
  usage?: UsageInfo;
  error?: string;
}

export interface SessionSummary {
  id: string;
  agent: string;
  messageCount: number;
  preview: string;
  createdAt: string;
  updatedAt: string;
  streaming: boolean;
}

export interface ModelsProvider {
  name: string;
  available: boolean;
  models: string[];
}

export interface ModelsConfig {
  default_provider: string;
  default_model: string;
  providers: ModelsProvider[];
}

export interface ToolCall {
  id: string;
  tool: string;
  arguments: Record<string, unknown>;
  result?: unknown;
  status: "calling" | "done" | "error";
  duration?: number;
}

// --- Contract rendering ---

export interface ModuleOutput {
  app_id: string;
  run_id: string;
  module_id: string;
  status: string;
  output: unknown;
  contract: string | null;
}

export interface DashboardCard {
  title: string;
  value: string | number;
  unit?: string | null;
  trend?: string | null;
  trend_direction?: "up" | "down" | "flat" | null;
  severity?: "info" | "warning" | "critical" | null;
}

export interface TableColumn {
  key: string;
  label: string;
  data_type: string;
  sortable: boolean;
}

export interface TableView {
  title: string;
  columns: TableColumn[];
  rows: Record<string, unknown>[];
  total_count: number;
  page: number;
  page_size: number;
}

export interface ProfileField {
  label: string;
  value: unknown;
  data_type: string;
}

export interface ProfileSection {
  heading: string;
  fields: ProfileField[];
}

export interface ProfileView {
  title: string;
  entity_type: string;
  entity_id: string;
  sections: ProfileSection[];
}

// --- Action Items ---

export interface ActionItemResponse {
  id: string;
  title: string;
  description: string;
  status: "open" | "in_progress" | "done" | "cancelled";
  priority: "low" | "medium" | "high" | "urgent";
  manager_id: string | null;
  property_id: string | null;
  tenant_id: string | null;
  due_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface ManagerNoteResponse {
  id: string;
  manager_id: string;
  content: string;
  created_at: string;
  updated_at: string;
}

// --- Entity Notes (KnowledgeGraph-backed) ---

export interface EntityNoteResponse {
  id: string;
  content: string;
  entity_type: string;
  entity_id: string;
  provenance: "user_stated" | "data_derived" | "inferred";
  source_doc?: string | null;
  created_by?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
}

// --- Search ---

export interface SearchHit {
  entity_id: string;
  entity_type: string;
  label: string;
  title: string;
  subtitle: string;
  score: number;
  metadata: Record<string, unknown>;
}

export interface SearchResponse {
  query: string;
  results: SearchHit[];
  total: number;
}

// --- Signals ---

export interface SignalSummary {
  signal_id: string;
  signal_type: string;
  severity: "critical" | "high" | "medium" | "low";
  entity_type: string;
  entity_id: string;
  entity_name: string;
  description: string;
  detected_at: string;
}

export interface SignalDigestEntity {
  entity_id: string;
  entity_type: string;
  entity_name: string;
  worst_severity: "critical" | "high" | "medium" | "low";
  signal_count: number;
  severity_counts: Record<string, number>;
  signals: SignalSummary[];
}

export interface SignalDigest {
  total_signals: number;
  total_entities: number;
  severity_counts: Record<string, number>;
  entities: SignalDigestEntity[];
}

export interface SignalExplain extends SignalSummary {
  provenance: string;
  evidence: Record<string, unknown>;
}

// --- Events / Audit ---

export interface ChangeEvent {
  entity_type: string;
  entity_id: string;
  action: "created" | "updated" | "removed";
  changes: Record<string, unknown>;
}

export interface ChangeSetSummary {
  changeset_id: string;
  source: string;
  report_type: string | null;
  document_id: string | null;
  timestamp: string;
  created: number;
  updated: number;
  removed: number;
  events: ChangeEvent[];
}

// --- Agents ---

export interface AgentMeta {
  name: string;
  description: string;
  version: string;
  primary: boolean;
  tags: string[];
}

// --- WebSocket ---

export interface WsEvent {
  event: string;
  app_id: string;
  run_id: string;
  timestamp: string;
  module_id?: string;
  [key: string]: unknown;
}
