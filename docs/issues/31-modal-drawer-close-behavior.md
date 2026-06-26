# Issue 31: Modal Drawer Close Behavior

## Context Pack

- `docs/prd.md`
- `docs/modules/user-interface.md`
- `docs/issues/26-chinese-labels-and-modal-actions.md`

## Category

Bug.

## Goal

Create/edit/generate actions should open as closeable overlays instead of permanently expanding the page layout.

## Scope

- Replace the current bare `<details class="action-drawer">` behavior with the smallest native closeable overlay pattern.
- Prefer native HTML/CSS and minimal JavaScript if needed.
- Overlay requirements:
  - Opens from the current section.
  - Has a visible 返回/关闭 control.
  - Does not navigate away before submit.
  - Submit keeps the current section context.
- Apply first to create-object actions used by the workflow sections.

## Acceptance Criteria

- Users can close the action overlay without submitting.
- The overlay appears visually as a floating modal/drawer, not as inline page expansion.
- Existing forms still submit successfully.
- Add one web/UI test or HTML assertion proving a close control exists.

## Out of Scope

- Custom component library.
- Animation polish.
