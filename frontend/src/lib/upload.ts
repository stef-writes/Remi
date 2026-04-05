import type { UploadResult } from "./types";

const REPORT_LABELS: Record<string, string> = {
  property_directory: "Property Directory",
  rent_roll: "Rent Roll",
  delinquency: "Delinquency",
  lease_expiration: "Lease Expiration",
};

function reportLabel(reportType: string): string {
  return REPORT_LABELS[reportType] ?? reportType.replace(/_/g, " ");
}

/**
 * Turn a raw UploadResult into a short, human-readable summary line.
 *
 * Examples:
 *   "Rent Roll — 42 units updated across 8 properties"
 *   "Property Directory — 12 properties and 3 managers registered"
 *   "Lease agreement — 14 passages indexed"
 */
export function summarizeUpload(r: UploadResult): string {
  const label = reportLabel(r.report_type);
  const { entities_extracted, relationships_extracted } = r.knowledge;

  if (r.kind === "tabular") {
    if (r.report_type === "property_directory") {
      return entities_extracted > 0
        ? `${label} — ${entities_extracted} properties registered`
        : `${label} — ${r.row_count} rows processed`;
    }
    if (entities_extracted > 0) {
      const parts = [`${entities_extracted} entities extracted`];
      if (relationships_extracted > 0) {
        parts.push(`${relationships_extracted} relationships`);
      }
      return `${label} — ${parts.join(", ")}`;
    }
    return `${label} — ${r.row_count} rows processed`;
  }

  if (r.kind === "text") {
    const pages = r.page_count > 0 ? `${r.page_count} pages, ` : "";
    return `${label} — ${pages}${r.chunk_count} passages indexed`;
  }

  return `${label} — uploaded`;
}

/**
 * Build a list of human-readable warnings from an upload result.
 * Returns empty array when everything is clean.
 */
export function uploadWarnings(r: UploadResult): string[] {
  const warnings: string[] = [];
  const k = r.knowledge;

  if (k.rows_rejected > 0) {
    warnings.push(`${k.rows_rejected} rows rejected`);
  }
  if (k.rows_skipped > 0) {
    warnings.push(`${k.rows_skipped} rows skipped`);
  }
  if (k.ambiguous_rows > 0) {
    warnings.push(`${k.ambiguous_rows} ambiguous rows`);
  }
  warnings.push(...k.validation_warnings);

  return warnings;
}

/**
 * Count review items that need human attention (action_needed severity).
 */
export function reviewItemsNeedingAction(r: UploadResult): number {
  return (r.knowledge.review_items ?? []).filter(
    (ri) => ri.severity === "action_needed",
  ).length;
}
