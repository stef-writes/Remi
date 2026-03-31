# REMI Data Directory

This directory contains sample reports and reference data used for development and testing.

## Structure

```
data/
  sample_reports/     # Real AppFolio exports from the director of PM
    rent_roll.*       # Rent Roll report
    delinquencies.*   # Delinquency report
    vacancies.*       # Vacancy report
```

## Usage

Drop weekly AppFolio exports here during development. These files are used to:
1. Derive accurate column mappings in `infrastructure/documents/report_schema.py`
2. Validate ingestion logic against real data shapes
3. Seed the demo environment with realistic data

## Security

Do NOT commit reports containing real tenant PII. Anonymize before committing,
or add `data/sample_reports/*.xlsx` / `data/sample_reports/*.csv` to `.gitignore`.
