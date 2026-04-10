#!/usr/bin/env bash
#
# Load Alex Budavich demo reports into a running REMI server.
#
# Usage:
#   ./scripts/load_demo_data.sh              # defaults to http://localhost:8000
#   ./scripts/load_demo_data.sh http://localhost:8001
#
# Reports are ingested in dependency order:
#   1. Property Directory  — creates managers + properties (source of truth)
#   2. Unit Directory      — creates units with physical data (beds, baths, sqft)
#   3. Rent Roll           — sets occupancy status, lease dates, market rent
#   4. Lease Expirations   — tenant names, lease terms, rent amounts
#   5. Delinquency         — balance observations for existing tenants
#
# The general ledger report is skipped — no rule-engine profile exists for it.

set -euo pipefail

API="${1:-http://localhost:8000}"
DIR="data/sample_reports/Alex_Budavich_Reports"

if ! curl -sf "$API/health" > /dev/null 2>&1; then
    echo "ERROR: Server not reachable at $API"
    echo "Start it first:  uv run remi serve"
    exit 1
fi

upload() {
    local file="$1"
    local label="$2"
    printf "  %-45s" "$label..."

    local response
    response=$(curl -sf -X POST "$API/api/v1/documents/upload" \
        -F "file=@$file" 2>&1) || {
        echo "FAILED"
        echo "    $response"
        return 1
    }

    local status report_type entities
    status=$(echo "$response" | python3 -c "import json,sys; print(json.load(sys.stdin).get('status','?'))" 2>/dev/null || echo "?")
    report_type=$(echo "$response" | python3 -c "import json,sys; print(json.load(sys.stdin).get('report_type','?'))" 2>/dev/null || echo "?")
    entities=$(echo "$response" | python3 -c "import json,sys; k=json.load(sys.stdin).get('knowledge',{}); print(k.get('entities_extracted',0))" 2>/dev/null || echo "?")

    echo "OK  (${report_type}, ${entities} entities)"
}

echo "Loading demo data into $API"
echo "─────────────────────────────────────────────────"

upload "$DIR/property_directory-20260330.xlsx"                   "Property Directory (managers + properties)"
upload "$DIR/unit_directory-20260409.xlsx"                       "Unit Directory (physical unit data)"
upload "$DIR/Rent Roll_Vacancy (1).xlsx"                        "Rent Roll / Vacancy (occupancy)"
upload "$DIR/Lease Expiration Detail By Month.xlsx"             "Lease Expirations (tenant leases)"
upload "$DIR/Delinquency.xlsx"                                  "Delinquency (balance observations)"

echo "─────────────────────────────────────────────────"

# Quick verification
manager_count=$(curl -sf "$API/api/v1/managers" | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('managers',[])))" 2>/dev/null || echo "?")
doc_count=$(curl -sf "$API/api/v1/documents" | python3 -c "import json,sys; print(len(json.load(sys.stdin).get('documents',[])))" 2>/dev/null || echo "?")

echo ""
echo "Loaded: ${doc_count} documents, ${manager_count} managers"
echo "View at: http://localhost:3000/managers"
