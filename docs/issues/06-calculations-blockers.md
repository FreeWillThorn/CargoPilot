# Issue 06: Package Calculations and Missing-Field Blockers

## Context Pack

- `docs/prd.md`
- `docs/modules/calculations-blockers.md`
- `docs/modules/orders-goods.md`

## Goal

Implement CBM/gross-weight calculations and stage-specific warning/blocker rules.

## Scope

- CBM calculation.
- Gross-weight calculation.
- Manual override fields.
- Stage-specific required-field checks.
- Warning versus blocker output.

## Acceptance Criteria

- CBM uses documented carton formula.
- Gross weight uses documented carton formula.
- Manual overrides take precedence where provided.
- Purchasing, container estimate, receiving, final document, and loading-complete checks return missing fields.
- Blockers prevent the next key milestone; warnings do not.
- Small runnable checks cover calculations and each stage rule.

## Out of Scope

- Container recommendation.
- Document generation.
