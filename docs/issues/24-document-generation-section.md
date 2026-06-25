# Issue 24: Document Generation Section

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/documents.md`
- `docs/modules/containers.md`

## Goal

Build 单证生成 as an Import Order-selected document workflow.

## Scope

- Top Context Selector chooses an Import Order.
- Only Admin Users can access 单证生成.
- Show document readiness, final-document blockers, generated version history, and download links.
- Generate draft/final Commercial Invoice and Packing List from modal or side drawer actions.
- Upload/track supporting compliance files from the selected Import Order context.
- Supporting compliance files can attach to the selected Import Order or to a specific Goods Line.
- Show Loading List download where relevant.

## Acceptance Criteria

- Final document generation is blocked when required fields are missing.
- Warehouse Users cannot access 单证生成.
- Draft generation is allowed and lists blockers.
- Generated xlsx/pdf versions are listed and downloadable.
- Certificates of origin, inspection certificates, and similar files are uploaded/tracked, not generated.
- Uploaded compliance files are visible from the selected Import Order's 单证生成 context.
- UI labels are Chinese-first, with document English names allowed beside Chinese labels.

## Out of Scope

- Word export.
- Custom template styling.
