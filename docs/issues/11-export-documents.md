# Issue 11: Commercial Invoice and Packing List

## Context Pack

- `docs/prd.md`
- `docs/modules/documents.md`
- `docs/modules/calculations-blockers.md`
- `docs/modules/orders-goods.md`
- `docs/modules/containers.md`

## Goal

Generate English Commercial Invoice and Packing List from confirmed order data.

## Scope

- Required-field blocking for final documents.
- Commercial Invoice generation.
- Packing List generation.
- Versioned generated documents.
- Excel and PDF export.
- Seller information from System Settings.

## Acceptance Criteria

- Final generation is blocked when required fields are missing.
- Draft generation can show missing blockers.
- Commercial Invoice includes documented fields and sales prices.
- Packing List summarizes by Goods Line.
- Generated document numbers use order number and version.
- Each generation creates a new version.
- Excel and PDF output smoke checks pass.

## Out of Scope

- Certificate of origin generation.
- Inspection certificate generation.
- Word export.
- Custom template styling.
