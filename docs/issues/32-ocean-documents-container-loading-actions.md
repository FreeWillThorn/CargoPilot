# Issue 32: Ocean Documents Container Loading Actions

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/documents.md`
- `docs/modules/containers.md`
- `docs/issues/24-document-generation-section.md`

## Category

Bug.

## Goal

Rename 单证生成 to 海运单证 and make container/loading actions use the same overlay action pattern as other sections.

## Scope

- Rename the left navigation label and page heading from 单证生成 to 海运单证.
- Keep document terms inside the page Chinese-first:
  - 商业发票
  - 装箱单
  - Loading List where industry-standard.
- Convert 新增集装箱 and 记录装箱 from always-visible forms to action buttons that open overlays.
- Preserve selected Import Order context after creating a container or loading record.

## Acceptance Criteria

- Left nav and page title show 海运单证.
- 新增集装箱 and 记录装箱 are opened from buttons/overlays.
- Submitting either action returns to the selected Import Order in 海运单证.
- Existing container/loading tests still pass.

## Out of Scope

- 3D container visualization.
