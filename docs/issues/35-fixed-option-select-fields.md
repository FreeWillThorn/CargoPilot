# Issue 35: Fixed Option Select Fields

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/orders-goods.md`
- `docs/modules/warehouse-receiving.md`
- `docs/modules/finance.md`

## Category

Bug.

## Goal

Fields with fixed business choices should be dropdowns instead of free-text inputs.

## Scope

- Replace free-text inputs with `<select>` where choices already exist in code:
  - Goods Logistics Status.
  - Compliance Status.
  - Warehouse type.
  - Arrival Exception Type.
  - Finance line kind/type.
  - Container type.
- Keep text inputs for genuinely open values such as notes, addresses, URLs, SKU/model.
- Preserve internal enum values on submit while showing Chinese labels where applicable.

## Acceptance Criteria

- Fixed-option fields cannot be mistyped through the UI.
- Visible labels are Chinese-first.
- Existing submissions still work.
- Tests cover at least two representative dropdown fields.

## Out of Scope

- Dynamic admin-managed option dictionaries.
