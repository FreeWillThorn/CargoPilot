# Issue 10: Container Planning and Loading Records

## Context Pack

- `docs/prd.md`
- `docs/modules/containers.md`
- `docs/modules/calculations-blockers.md`
- `docs/modules/orders-goods.md`

## Goal

Implement container planning and actual loading records.

## Scope

- 20GP/40GP/40HQ recommendation from CBM and gross weight.
- Containers under an Import Order.
- Loading Records.
- Goods Line splits across Containers.
- Simple loading list export.

## Acceptance Criteria

- One Import Order can have multiple Containers.
- One Container cannot mix multiple Import Orders.
- Loading Records store container type, container number, seal number, date, Goods Lines, loaded carton counts, photos, and notes.
- Same Goods Line can split across multiple Containers.
- Simple loading list includes container number, seal number, Goods Lines, cartons, CBM, and gross weight.
- Small runnable checks cover recommendation, split loading, and totals.

## Out of Scope

- Visual loading diagram.
- 3D container optimization.
- Mixed-order containers.
