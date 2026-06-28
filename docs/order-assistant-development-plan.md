# Order Assistant Development Plan

## Goal

Build the Order Assistant MVP in small issue-sized slices, with the PRD as the index and existing workflow sections preserved.

## Context Pack For All Issues

- `docs/prd.md`
- `docs/prd-order-assistant.md`
- `docs/modules/order-assistant.md`
- `docs/modules/user-interface.md`
- `CONTEXT.md`
- `docs/adr/0003-fixed-multi-agent-order-assistant.md`

## Phase 1 Modules

- Order Assistant entry inside selected `订单详情`.
- Contextual AI Action Buttons in `订单详情`, `货物详情`, `海运单证`, and `成本利润`.
- Background Assistant Run lifecycle.
- Router using task templates plus source rules.
- Structured Intake Agent / 结构化录入 Agent.
- Order Review Agent / 订单检查 Agent.
- Goods Review Agent / 货物资料检查 Agent.
- Compliance Risk Agent / 合规/单证风险 Agent.
- Document Draft Agent / 单证草稿 Agent.
- Profit Risk Agent / 利润风险 Agent.
- Coordinator / 汇总器.
- Review Request and Change Draft confirmation flow.
- DeepSeek JSON integration plus demo mode.

## Phase 2 Modules

- Batch confirmation for low-risk Change Drafts.
- Configurable routing UI.
- Saved assistant run templates.
- Configurable compliance keywords.
- Configurable profit thresholds and required fee categories.
- AI cost dashboard.
- Prompt management UI.
- Optional dedicated assistant workspace.
- Better arbitrary Excel/PDF/chat extraction after real sample patterns are known.

## Phase 1 Issues

1. **Assistant Data Contract**
   Define Assistant Run, Assistant Suggestion, Review Request, Change Draft, Source Reference, model usage, statuses, Chinese UI labels, the shared structured JSON envelope used by every agent, and fields needed to enforce task, permission, context, tool, output, and responsibility isolation.
   Issue: `docs/issues/53-order-assistant-data-contract.md`

2. **Background Assistant Run**
   Add queued/running/succeeded/failed runs, retry for failed runs, prompt version recording, model usage recording, and demo mode when no DeepSeek key exists.
   Issue: `docs/issues/54-order-assistant-background-runs.md`

3. **Router And Demo Agents**
   Implement task-template plus source-rule routing for AI Action Buttons and uploaded sources. Add demo versions of Structured Intake Agent, Order Review Agent, Goods Review Agent, Compliance Risk Agent, Document Draft Agent, Profit Risk Agent, and Coordinator, each following the Agent Contracts, documented business goals, and Agent Isolation Standard.
   Issue: `docs/issues/55-order-assistant-router-demo-agents.md`

4. **Order Assistant Entry And Drawer**
   Add the Order Assistant entry inside selected `订单详情` and the right-side AI drawer for contextual buttons. Show in-progress runs, grouped Review Requests, suggestion levels, source references, and Chinese statuses.
   Issue: `docs/issues/56-order-assistant-entry-drawer.md`

5. **Review Request To Change Draft Flow**
   Let Admin Users ignore, mark follow-up, approve for draft, reject drafts, or confirm drafts. Confirmation UI shows original value, AI suggested value, and administrator final value.
   Issue: `docs/issues/57-order-assistant-review-draft-flow.md`

6. **Structured Intake Drafts**
   Support Excel/PDF/chat-record intake into proposed goods-line drafts, finance drafts, and document-data drafts. Use the completed Chinese goods-list workbook sample, or an equivalent committed/generated fixture, as one acceptance test. Do not create master-data drafts.
   Issue: `docs/issues/58-order-assistant-structured-intake.md`

7. **Compliance And Goods Review**
   Add the first compliance keyword constants and checks for goods names, materials, categories, HS Code, Customs English Name, carton count, gross weight, CBM, Shipping Mark, and Domestic Tracking Number.
   Issue: `docs/issues/59-order-assistant-compliance-goods-review.md`

8. **Document Draft Agent**
   Prepare Commercial Invoice and Packing List drafts from confirmed data. Official documents still require Admin User confirmation.
   Issue: `docs/issues/60-order-assistant-document-draft-agent.md`

9. **Profit Risk Agent**
   Add fixed MVP profit checks: margin below target, costs without customer charges, missing sea freight, missing warehouse fee, missing document/compliance fee, low quote, and missing exchange rate.
   Issue: `docs/issues/61-order-assistant-profit-risk-agent.md`

10. **DeepSeek Integration**
    Replace demo agent responses with validated DeepSeek JSON responses where appropriate. Keep demo mode for development and demos.
    Issue: `docs/issues/62-order-assistant-deepseek-integration.md`

## Phase 2 Holding Pen

- Batch confirmation for low-risk Change Drafts.
- Configurable routing UI after task templates and source rules stabilize.
- Configurable compliance keywords and profit thresholds.
- AI cost dashboard.
- Prompt management UI.
- Dedicated assistant workspace if the embedded order entry becomes crowded.

## Development Rule

Each issue should be developed and committed independently. Do not start with the full DeepSeek integration; build the data contract, run lifecycle, Router, Coordinator, and demo mode first so UI and workflow can be tested without external model calls.
