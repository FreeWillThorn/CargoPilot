# 订单智能体 Development Plan

## Context Pack

Every future issue should include:

- `CONTEXT.md`
- `docs/prd-order-agent.md`
- `docs/modules/order-agent.md`
- `docs/adr/0005-order-agent-can-start-without-order.md`
- `docs/adr/0006-order-agent-uses-retained-conversations.md`
- `docs/adr/0007-order-agent-requires-live-model.md`

## MVP Modules

1. **Section Shell**
   Add first-level `订单智能体` navigation above `AI资料收集箱`, with retained-conversation layout, optional Import Order selector, upload control, natural-language input, and empty-state UI.

2. **Conversation Storage**
   Add minimal `order_agent_conversations`, `order_agent_messages`, `order_agent_steps`, and `order_agent_drafts` storage. Keep messages, source summaries, model responses, trace steps, draft snapshots, and statuses.

3. **Attachment Summary Pipeline**
   Reuse existing local parsing where possible for Excel/PDF/TXT/pasted text. Record every parse step in Agent Processing Trace. PDF OCR is in MVP; image OCR is not.

4. **Live Model Adapter**
   Reuse the existing DeepSeek configuration from 基础资料. Add Order Agent-specific model-call helpers for the three Agent contracts. No separate settings page.

5. **Task Understanding Agent**
   Call the live model to decide data entry, risk prompting, missing information, blocked/out-of-scope requests, and next plan. No local fallback conclusions.

6. **Data Entry Agent**
   Call the live model to produce allowlisted draft candidates: Import Order, Goods Line, Supplier, Consignee, and field updates. Unknown fields become unmapped information.

7. **Draft Review And Execution**
   Show editable draft forms, duplicate-risk hints for master data, and a two-step confirmation chain. On confirmation, reuse existing business functions to create/reuse Supplier and Consignee records, create Import Orders, create Goods Lines, and apply allowed updates.

8. **Order Risk Agent**
   Call the live model for risk prompts only when requested or clearly implied. Group results by Supplier when known. Do not create system Change Drafts from risks.

9. **Processing Trace UI**
   Show local parsing, model calls, success/failure, selected Agents, summaries, blocked steps, retry buttons, and collapsible raw structured responses.

10. **Demo And Manual Test Pack**
    Create a manual test script for the primary order-creation demo and secondary risk-prompt demo using real DeepSeek API. Automated tests should mock DeepSeek but verify that model calls are required.

## Suggested Issue Split

Use one focused issue per module above. Each issue should include the Context Pack, its single scope, acceptance criteria, and the smallest relevant tests.

## Testing Gate

Before marking MVP complete:

- automated tests pass with mocked model calls
- model unavailable fails the whole run
- no local risk or data-entry fallback creates user-facing results
- wide draft tables and long trace lists scroll
- retained conversation survives refresh
- primary demo scenario passes with real DeepSeek
- secondary risk scenario passes with real DeepSeek

## Phase 2 Triggers

Only start Phase 2 after the MVP demo is stable and real use shows repeated need for:

- image/chat screenshot OCR
- supplier follow-up workflow
- finance/container/customs/document draft expansion
- delete drafts
- richer master-data merge
- model-cost dashboard
- configurable orchestration
