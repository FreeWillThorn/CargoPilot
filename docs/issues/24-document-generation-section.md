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
- Show document readiness, final-document blockers, generated version history, and download links.
- Generate draft/final Commercial Invoice and Packing List from modal or side drawer actions.
- Upload/track supporting compliance files from the selected Import Order context.
- Show Loading List download where relevant.

## Acceptance Criteria

- Final document generation is blocked when required fields are missing.
- Draft generation is allowed and lists blockers.
- Generated xlsx/pdf versions are listed and downloadable.
- Certificates of origin, inspection certificates, and similar files are uploaded/tracked, not generated.
- UI labels are Chinese-first, with document English names allowed beside Chinese labels.

## Out of Scope

- Word export.
- Custom template styling.
