# Container Planning and Loading Module

## Scope

Estimate container needs, record actual Containers, and track Loading Records.

## Decisions

- MVP recommends 20GP, 40GP, or 40HQ from total CBM and gross weight.
- No advanced loading optimization in MVP.
- One Import Order can use multiple Containers.
- One Container cannot mix multiple Import Orders in MVP.
- Loading Records include container type, container number, seal number, loading date, loaded Goods Lines, loaded carton counts, photos, and notes.
- Same Goods Line can split across multiple Containers.
- Generate simple loading list with container number, seal number, Goods Lines, cartons, CBM, and gross weight.

## Later

Visual loading diagram and 3D container optimization.

## Test Focus

- Container recommendation.
- Goods Line split across Containers.
- Loading list totals.
