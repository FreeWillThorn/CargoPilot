# Development Flow

## Per-Issue Context Rule

Each issue has a **Context Pack**. A development session should read only:

1. `docs/prd.md`
2. The issue file
3. The module docs named in the issue
4. `CONTEXT.md` or ADRs only when listed

Do not read the full requirements history unless the issue explicitly asks for it.

## Skill Route

Use `/implement` for each issue in a fresh session.

If `/implement` is unavailable in that session, use a normal implementation request and paste the issue's Context Pack.

Use frontend skills only for UI-heavy issues:

- `build-web-apps:frontend-app-builder` for building new UI screens.
- `build-web-apps:frontend-testing-debugging` for browser verification and UI regressions.
- `build-web-apps:react-best-practices` if the chosen stack is React or Next.js.

Use document/PDF/spreadsheet skills only for file-generation issues:

- `documents:documents` for Word-like document work.
- `pdf:pdf` for PDF rendering/verification.
- `spreadsheets:Spreadsheets` for Excel import/export and generated spreadsheets.

## Git Rule

One issue, one focused commit. Releases get tags. Production fixes prefer `git revert` before forward-fixing.
