# Issue 34: Compliance File Upload

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/documents.md`
- `docs/issues/24-document-generation-section.md`

## Category

Bug.

## Goal

海运单证 must allow users to upload and track compliance files such as certificates of origin and inspection certificates.

## Scope

- Add an upload action in the selected Import Order document context.
- Store file metadata in the existing `files` table.
- Files may attach to:
  - selected Import Order
  - selected Goods Line under that Import Order
- Required file categories for MVP:
  - 产地证
  - 检验证书
  - 防疫/检疫文件
  - 其他合规文件
- Keep certificates uploaded/tracked only; do not generate them.

## Acceptance Criteria

- Admin can upload or register a compliance file from 海运单证.
- Uploaded/registered file appears in 合规文件列表 for the selected Import Order.
- Warehouse User cannot access the page.
- Tests cover adding a compliance file and seeing it in the list.

## Out of Scope

- File expiry reminders.
- External document signing.
