# Agent Instructions

- Before closing implementation work, commit and push the completed changes to `origin` on GitHub unless the user explicitly says not to.
- `progress.json` is temporary per subagent run. Create a fresh `progress.json` only when starting subagent coordination, do not reuse an existing one across sessions, and delete it before closing the work.
- If pushing is blocked during a subagent run, record the blocker while the temporary file is active and state it in the final response; still delete `progress.json` before closing unless the user explicitly asks to keep it.

## User Development Habits

- Start with PRD and requirement clarification for fuzzy product work. Ask several focused questions at once when that speeds up decisions.
- Turn approved requirements into small, independent issues. Each issue should include a Context Pack so future agents read only the PRD, the issue, and directly relevant module docs.
- Develop MVP-first. Ship the simplest complete version that supports the workflow, and record later enhancements instead of building speculative features.
- Keep one focused commit per issue. Push after each completed issue. Tag releases. For production regressions, prefer `git revert` to restore stable behavior before forward-fixing.
- Preserve Git hygiene: do not commit unrelated untracked files, generated outputs, local templates, or user-provided scratch files unless explicitly requested.
- Prefer existing project patterns and helpers over new abstractions. Use standard library and native browser controls before adding dependencies.
- Use business workflow navigation, not database-table navigation. Screens should be organized around what the user is doing.
- UI labels should be Chinese-first and domain-specific. Do not expose raw database field names to users.
- Large tables and long sections need scroll containers so pages remain usable with real data volume.
- CRUD should be consistent: compact icon actions, drawer/modal forms, close/return behavior, and staying in the current section after save.
- Select fields, inline status dropdowns, upload controls, and date inputs should use native controls unless the project already has a stronger component.
- Keep roles simple unless requested otherwise. Admin gets full access; restricted roles only see and edit the workflow they are responsible for.
- Verify non-trivial changes with the smallest relevant automated test. For frontend behavior, also do a browser smoke check when layout or navigation changes.
- Keep final reports concise: say what changed, what was verified, commit hash, and any skipped checks.
