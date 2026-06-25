# Issue 26: Chinese Labels and Modal Actions

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`

## Goal

Remove raw database field names from the browser UI and standardize object actions as modal or side drawer workflows.

## Scope

- Replace visible raw names such as `customs_en_name`, `target_markup`, `carton_gross_weight_kg`, and `domestic_tracking_no` with Chinese industry labels.
- Keep accepted English terms where appropriate: FOB, CIF, HS Code, SKU, CBM, Commercial Invoice, Packing List.
- Create a shared label map or simple helper for field labels.
- Convert create/edit/upload/generate/status-change actions to modal or side drawer UI patterns where practical.
- Use right-side drawers for large forms and centered modals for small confirmations.
- Keep tables focused on summary columns; dense fields move into grouped forms.

## Acceptance Criteria

- No visible form labels or table headers expose internal database names.
- Main UI is Chinese-first.
- Each Workflow Section uses buttons for current-object actions instead of separate CRUD navigation.
- Goods Line editing, costs/charges, receiving records, loading records, and document generation use right-side drawers.
- Delete/cancel/irreversible status confirmations use centered modals.
- Tests cover at least one representative page for absence of raw field names and presence of Chinese labels.

## Out of Scope

- Full visual redesign.
- Custom component library.
