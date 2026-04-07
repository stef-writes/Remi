// --- Property Managers (director-level) ---

export interface ManagerMetrics {
  total_units: number;
  occupied: number;
  vacant: number;
  occupancy_rate: number;
  total_actual_rent: number;
  total_market_rent: number;
  loss_to_lease: number;
  vacancy_loss: number;
  open_maintenance: number;
  expiring_leases_90d: number;
}

export interface ManagerListItem {
  id: string;
  name: string;
  email: string;
  company: string | null;
  property_count: number;
  metrics: ManagerMetrics;
  delinquent_count: number;
  total_delinquent_balance: number;
  expired_leases: number;
  below_market_units: number;
  emergency_maintenance: number;
}

export interface ManagerPropertySummary {
  property_id: string;
  property_name: string;
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
  property_count: number;
  metrics: ManagerMetrics;
  delinquent_count: number;
  total_delinquent_balance: number;
  expired_leases: number;
  below_market_units: number;
  emergency_maintenance: number;
  properties: ManagerPropertySummary[];
  top_issues: ManagerUnitIssue[];
}

// --- Dashboard Overview ---

export interface ManagerOverview {
  manager_id: string;
  manager_name: string;
  property_count: number;
  metrics: ManagerMetrics;
}

export interface PropertyOverview {
  property_id: string;
  property_name: string;
  address: string;
  manager_id: string | null;
  manager_name: string | null;
  total_units: number;
  occupied: number;
  vacant: number;
  occupancy_rate: number;
  monthly_rent: number;
  market_rent: number;
  loss_to_lease: number;
  open_maintenance: number;
}

export interface DashboardOverview {
  total_properties: number;
  total_units: number;
  occupied: number;
  vacant: number;
  occupancy_rate: number;
  total_monthly_rent: number;
  total_market_rent: number;
  total_loss_to_lease: number;
  properties: PropertyOverview[];
  total_managers: number;
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
  balance_owed: number;       // from latest BalanceObservation
  balance_0_30: number;       // from latest BalanceObservation
  balance_30_plus: number;    // from latest BalanceObservation
  last_payment_date: string | null;
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
  occupancy_status: string | null;  // derived from lease history
  days_vacant: number | null;       // computed from last lease end date
  market_rent: number;
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

// --- Property ---

export interface PropertyDetail {
  id: string;
  name: string;
  address: Record<string, string>;
  property_type: string;
  year_built: number;
  manager_id: string | null;
  manager_name: string | null;
  owner_id: string | null;
  owner_name: string | null;
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

export interface DuplicateInfo {
  existing_id: string;
  existing_filename: string;
  uploaded_at: string;
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
  duplicate?: DuplicateInfo | null;
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

// --- Events / Audit ---

export interface FieldChange {
  field: string;
  old_value: unknown;
  new_value: unknown;
}

export interface ChangeEvent {
  entity_type: string;
  entity_id: string;
  change_type: "created" | "updated" | "removed";
  source: string;
  timestamp: string;
  fields: FieldChange[];
}

export interface ChangeSetSummary {
  id: string;
  source: string;
  source_detail: string;
  adapter_name: string;
  report_type: string | null;
  document_id: string;
  timestamp: string;
  summary: { created: number; updated: number; unchanged: number; removed: number };
  total_changes: number;
  is_empty: boolean;
  events: ChangeEvent[];
  unchanged_ids: string[];
}

// --- Agents ---

export interface AgentMeta {
  name: string;
  description: string;
  version: string;
  primary: boolean;
  tags: string[];
}

// --- Knowledge Graph Visualization ---

export interface GraphNode {
  id: string;
  type_name: string;
  label: string;
  properties: Record<string, unknown>;
}

export interface GraphEdge {
  source_id: string;
  target_id: string;
  link_type: string;
}

export interface GraphSnapshot {
  nodes: GraphNode[];
  edges: GraphEdge[];
  counts: Record<string, number>;
  edge_counts: Record<string, number>;
  total_nodes: number;
  total_edges: number;
}

export interface GraphSubgraph {
  center_id: string;
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface OperationalNode {
  id: string;
  kind: "step" | "cause" | "effect" | "policy" | "signal" | "workflow";
  label: string;
  process: string;
  properties: Record<string, unknown>;
}

export interface OperationalEdge {
  source_id: string;
  target_id: string;
  link_type: string;
}

export interface OperationalGraph {
  nodes: OperationalNode[];
  edges: OperationalEdge[];
  processes: string[];
}

// --- Meeting Brief ---

export interface MeetingBriefAction {
  title: string;
  description?: string;
  priority?: "urgent" | "high" | "medium" | "low";
  owner: "manager" | "director" | "both";
  timeframe: string;
}

export interface MeetingAgendaItem {
  topic: string;
  severity: "high" | "medium" | "low";
  talking_points: string[];
  questions: string[];
  suggested_actions: MeetingBriefAction[];
}

export interface MeetingBrief {
  manager_name: string;
  summary: string;
  agenda: MeetingAgendaItem[];
  positives: string[];
  follow_up_date: string;
}

export interface MeetingBriefAnalysis {
  themes: {
    id: string;
    title: string;
    severity: string;
    summary: string;
    details?: string;
    affected_properties: string[];
    monthly_impact: number;
  }[];
  positive_notes: string[];
  data_gaps?: string[];
}

export interface MeetingBriefResponse {
  id: string;
  manager_id: string;
  snapshot_hash: string;
  brief: MeetingBrief;
  analysis: MeetingBriefAnalysis;
  focus: string | null;
  generated_at: string;
  usage: { prompt_tokens: number; completion_tokens: number };
}

export interface MeetingBriefListResponse {
  briefs: MeetingBriefResponse[];
  total: number;
  current_snapshot_hash: string | null;
}

// --- Trends (time-series) ---

export interface DelinquencyTrendPeriod {
  period: string;
  total_balance: number;
  tenant_count: number;
  avg_balance: number;
  max_balance: number;
}

export interface DelinquencyTrend {
  manager_id: string | null;
  periods: DelinquencyTrendPeriod[];
  period_count: number;
  direction: "improving" | "worsening" | "stable" | "insufficient_data";
}

export interface OccupancyTrendPeriod {
  period: string;
  total_units: number;
  occupied: number;
  vacant: number;
  occupancy_rate: number;
}

export interface OccupancyTrend {
  manager_id: string | null;
  property_id: string | null;
  periods: OccupancyTrendPeriod[];
  period_count: number;
  direction: "improving" | "worsening" | "stable" | "insufficient_data";
}

export interface RentTrendPeriod {
  period: string;
  avg_rent: number;
  median_rent: number;
  total_rent: number;
  unit_count: number;
}

export interface RentTrend {
  manager_id: string | null;
  property_id: string | null;
  periods: RentTrendPeriod[];
  period_count: number;
  direction: "improving" | "worsening" | "stable" | "insufficient_data";
}

export interface MaintenanceTrendPeriod {
  period: string;
  opened: number;
  completed: number;
  net_open: number;
  total_cost: number;
  avg_resolution_days: number | null;
  by_category: Record<string, number>;
}

export interface MaintenanceTrend {
  manager_id: string | null;
  property_id: string | null;
  unit_id: string | null;
  periods: MaintenanceTrendPeriod[];
  period_count: number;
  direction: "improving" | "worsening" | "stable" | "insufficient_data";
}

// --- WebSocket ---

export interface WsEvent {
  type: string;
  data: Record<string, unknown>;
  [key: string]: unknown;
}
