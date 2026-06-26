# Issue 41: Real Upload Controls

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/modules/documents.md`
- `docs/modules/warehouse-receiving.md`
- `docs/modules/containers.md`
- `docs/issues/34-compliance-file-upload.md`

## Category

Bug.

## Goal

Upload actions should use browser file upload controls instead of path-only text inputs.

## Scope

- Add `<input type="file">` controls for:
  - compliance files in 海运单证
  - receiving photos in 仓库盘点
  - loading photos in 海运单证
- Support multipart form parsing in the stdlib HTTP server.
- Store uploaded files under existing `data/uploads/...` folders.
- Keep path registration as an optional fallback only if cheap.
- Record file metadata in the existing `files` table.

## Acceptance Criteria

- Admin can upload a compliance file through a browser file input.
- Warehouse User can upload receiving photo through a browser file input.
- Uploaded files are copied into `data/uploads/...` and appear in the relevant file list/metadata.
- Existing path-based tests either keep passing or are updated to multipart tests.

## Out of Scope

- Drag-and-drop upload.
- Antivirus/file scanning.
- External object storage.
