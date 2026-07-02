# 订单智能体 MVP Module

## Positioning

`订单智能体` is a new Admin-only Workflow Section for turning natural-language business goals and uploaded materials into controlled order work. `AI资料收集箱` remains available as a fallback demo path while this MVP is developed, but the Order Agent is the preferred direction if it succeeds.

The MVP has two goals:

- data entry / 资料录入
- order risk prompting / 风险提示

It does not use fixed Task Templates. The Task Understanding Agent decides which goal applies from the user's natural-language input first, attachment summaries second, and current order context third.

## Context Pack

Future PRD, development-plan, issue, and implementation work for `订单智能体` should start from:

- `CONTEXT.md`
- `docs/modules/order-agent.md`
- `docs/adr/0005-order-agent-can-start-without-order.md`
- `docs/adr/0006-order-agent-uses-retained-conversations.md`
- `docs/adr/0007-order-agent-requires-live-model.md`

Doc ownership:

- `CONTEXT.md` is glossary only.
- `docs/adr/` records hard-to-reverse architecture decisions.
- `docs/modules/order-agent.md` records the current MVP module contract.

## Demo Scenario

Use this as the primary interview demonstration path for the MVP:

```text
No Import Order selected
→ Admin User uploads supplier material or pastes chat records
→ Admin User enters: "帮我根据这些资料创建一个订单"
→ Agent Processing Trace shows:
   1. local attachment parsing
   2. Task Understanding Agent: data entry needed, risk prompting not needed
   3. Data Entry Agent extracts order, goods, Supplier, and Consignee drafts
   4. missing destination port or customer information moves the conversation to waiting_for_input
→ Admin User adds: "目的港 Rotterdam，客户 Eldar"
→ Order Agent merges the conversation into:
   - Order Creation Draft
   - Minimal Goods Line Drafts
   - Supplier / Consignee Master Data Drafts
→ Admin User generates pending drafts
→ Admin User confirms execution
→ CargoPilot creates the Import Order and related confirmed records
```

This scenario should be used later in PRD, testing, and interview demo preparation.

Secondary interview demonstration path:

```text
Existing Import Order selected
→ Admin User enters: "帮我检查这个订单清关和单证风险"
→ Task Understanding Agent: risk prompting needed, data entry not needed
→ Order Risk Agent calls the live model with current order, goods, supplier grouping, destination/origin, and source summaries
→ UI groups risks by Supplier when known
→ Each risk shows basis, affected goods, suggested documents/actions, confidence, and review need
→ Raw structured model response is available in a collapsed details section
```

## Entry Modes

The Order Agent can run in two modes:

- **No selected Import Order**: create an Order Creation Draft from supplied materials.
- **Selected Import Order**: create Order Update Drafts or related Goods Line / master-data drafts for the selected Import Order.

Uploading files without a natural-language prompt is allowed. The default interpretation is data entry. Risk prompting only runs when the user explicitly or clearly implies risk review, such as asking about customs, documents, clearance, certificates, or whether the order can proceed.

Each run can include multiple files as one conversation input batch. MVP supported inputs:

- `.xlsx` / `.xls`
- `.pdf`
- `.txt`
- pasted text

PDF OCR is in MVP. Image OCR for `.png`, `.jpg`, and chat screenshots is Phase 2.

The Agent Processing Trace must show each file separately, including parse success, parse failure, extracted row/page counts when known, and whether the model continued with the available summaries.

## Live Model Requirement

The MVP requires a live configured model call for Task Understanding, Data Entry, and Risk Prompting. If the model is unavailable, unconfigured, times out, or returns unusable structured output, the run fails clearly.

Local parsing may read Excel, PDF, OCR text, and attachment metadata to prepare source summaries for the model. It must be shown in the Agent Processing Trace. Local parsing must not generate user-facing data-entry applications or risk findings when the model fails.

Use the existing DeepSeek configuration in 基础资料. Do not add a separate model settings page for `订单智能体`.

Product access is Admin-only. MVP implementation should reuse existing Admin checks and must not introduce a new role or fine-grained permission system.

## Retained Conversations

The Order Agent is not a stateless prompt form. Each conversation retains:

- user chat messages
- uploaded source summaries
- extracted fields
- missing-field questions
- proposed drafts
- model responses
- Agent Processing Trace

Each Agent Processing Trace step keeps:

- agent name
- request summary
- model status
- business summary
- raw structured model response when available
- error message when failed
- timestamp

Do not store API keys or HTTP headers in the conversation.

If the user omits required information, the UI keeps the conversation and lets the Admin User upload or type more later.

Conversation statuses:

- draft / 草稿中
- waiting_for_input / 待补充
- draft_ready / 已生成草稿
- closed / 已关闭

## Browser Layout

The `订单智能体` page keeps the retained conversation list on the left and the selected conversation workspace on the right.

The selected workspace is split into two stacked areas:

- 当前对话: selected conversation metadata, messages, upload/text inputs, and Agent Processing Trace.
- 结果区: task understanding, source summaries, risk prompts, and data-entry drafts.

The result area intentionally sits below the current conversation panel instead of inside its scroll container, because model output and draft cards can be long. The left conversation list uses a taller scroll container so Admin Users can switch conversations without scrolling through result content first.

## Model Agents

The MVP uses three model agents.

**Task Understanding Agent / 任务理解 Agent**

Reads the user's natural language, attachment summaries, and optional current Import Order context. It decides:

- user goal
- whether Data Entry Agent should run
- whether Order Risk Agent should run
- missing information
- blocked or out-of-scope requests
- next plan

It may refuse unsupported, out-of-scope, cross-order, or high-risk requests.

**Data Entry Agent / 资料录入 Agent**

Creates structured draft candidates from the conversation and sources:

- Order Creation Draft
- Order Update Draft
- Minimal Goods Line Draft
- Master Data Draft for Supplier or Consignee
- field update drafts for an existing Import Order or Goods Line
- missing-field questions

At least one Chinese or English goods name is enough to create a Minimal Goods Line Draft. Other fields can remain empty and appear as missing information.

The model may identify fields beyond the current system write model. The UI may show all recognized information, but only allowlisted system fields can enter confirmable drafts. Unknown fields appear as unmapped information rather than silently changing the data model.

Allowlisted draft fields for MVP:

Import Order:

- `order_no` is system-generated only; the model must not write it.
- `consignee_id` or Consignee draft reference
- `destination_port`
- `trade_term`
- `expected_loading_date`
- `internal_notes`

Goods Line:

- `supplier_id` or Supplier draft reference
- `customer_item_no`
- `product_url`
- `cn_name`
- `en_name`
- `customs_en_name`
- `sku_or_model`
- `category`
- `hs_code`
- `quantity`
- `unit`
- `carton_count`
- `units_per_carton`
- `carton_length_cm`
- `carton_width_cm`
- `carton_height_cm`
- `carton_gross_weight_kg`
- `gross_weight`
- `volume_cbm`
- `shipping_mark`
- `purchase_unit_price`
- `purchase_currency`
- `logistics_status`
- `notes`

Supplier / Consignee:

- `name`
- `contact_person`
- `phone`
- `email`
- `address`
- `notes`

Out of MVP write fields:

- `order_status`
- `compliance_status`
- finance fields beyond Goods Line purchase price
- warehouse receiving fields
- loading fields
- document-generation fields

**Order Risk Agent / 风险提示 Agent**

Uses the live model to identify customs, document, compliance, or workflow risks. Risk categories are open-ended and model-determined, not locally hard-coded.

Each risk must include:

- risk name
- basis
- affected Goods Lines or source items
- affected Supplier grouping when known
- suggested documents or actions
- confidence
- whether Admin review is needed

The system may format, group, and deduplicate model output. It must not use local keyword fallback to invent risk findings.

## Draft And Confirmation Rules

All writes require confirmation. The MVP keeps a two-step confirmation chain:

1. AI 建议 / business suggestion
2. 待确认草稿 / confirm execution

The Order Agent may generate drafts for:

- creating an Import Order
- updating the selected Import Order
- creating Goods Lines
- updating Goods Line fields
- creating Supplier or Consignee master-data records

MVP draft types:

- `import_order_create`
- `import_order_update`
- `goods_line_create`
- `goods_line_update`
- `supplier_create_or_reuse`
- `consignee_create_or_reuse`

Out of MVP:

- finance drafts
- container drafts
- Customs Goods Version drafts
- document generation drafts
- warehouse receiving drafts
- loading record drafts
- compliance file drafts
- deletion drafts

Master Data Drafts must show possible duplicate risk. MVP duplicate checks can use simple name normalization, containment, phone, or email matching. The model may comment on likely duplicates, but the UI must show the basis.

Execution rules for Order Creation Drafts:

- Prefer reusing existing Supplier and Consignee records when duplicate checks match.
- Create Supplier or Consignee records only after Admin confirmation.
- Create or reuse master data before creating the Import Order and Goods Lines.
- Do not let the model invent the Import Order number. Use the existing system order-number creation path or a system-generated temporary number.
- After confirmation, stay in `订单智能体` and show an execution summary. Do not auto-jump to `订单详情` or add a special "open order" flow in MVP.

Deletion is not supported in MVP. The agent may recognize deletion intent and show a high-risk unsupported-operation message, but it must not create deletion drafts.

## Data Storage

Use new minimal Order Agent storage concepts for the conversation workflow:

- `order_agent_conversations`
- `order_agent_messages`
- `order_agent_steps`
- `order_agent_drafts`

Do not force the Order Agent UI into the old AI资料收集箱 three-lane Assistant Run / Review Request / Change Draft shape. When the Admin User confirms execution, reuse existing business functions such as Import Order creation, Goods Line creation, Supplier creation, Consignee creation, and update helpers.

## Risk Prompt Output

Risk prompts do not create system Change Drafts in MVP. They create business risk suggestions only.

Example:

```text
风险：食品接触材料可能需要声明/测试报告
依据：货物名包含杯、茶壶，目的港为 Rotterdam
涉及供应商：供应商 A
涉及货物：白杯、黑杯、茶壶
建议动作：向供应商 A 索要食品接触声明或测试报告
状态：待人工处理
```

Risk suggestion statuses in MVP:

- pending / 待处理
- ignored / 已忽略

Do not build supplier follow-up statuses, reminder workflows, or supplier-message sending in MVP.

## UI Shape

The Order Agent UI is a business workbench, not a pure chat window.

Navigation:

- Add `订单智能体` as a first-level Workflow Section.
- Place it above `AI资料收集箱` because it is the preferred new agent workflow while AI资料收集箱 remains the fallback demo path.

Recommended layout:

- left: retained conversation list with statuses such as 草稿中, 待补充, 已生成草稿, 已关闭
- right/top: optional Import Order selector, upload control, natural-language input
- right/middle: Agent Processing Trace
- right/results: business conclusion, data-entry applications, risk suggestions, missing information, pending drafts, execution summary

Do not copy the AI资料收集箱 three-lane layout. Agent Processing Trace is the run history for the current conversation.

Drafts must be editable before confirmation. Use simple forms for MVP. Any table or large draft list must live inside a scroll container so long goods lists, supplier groups, and model-return details do not overflow or become unreachable.

MVP does not add a dedicated "re-check after edit" action. If the Admin User wants another model check after editing draft values, they should continue the conversation with a new message.

The Agent Processing Trace must show every meaningful step:

- local attachment reading
- Excel/PDF/OCR parsing
- attachment summary creation
- Task Understanding Agent call
- model success or failure
- selected downstream agents
- Data Entry Agent call
- Order Risk Agent call
- generated outputs
- blocked steps

Failed model or parsing steps may be manually retried from the failed step, reusing the same conversation and input batch. Do not add automatic retry or model switching in MVP.

Model responses are shown in two layers:

- default business summary
- collapsible raw structured response for inspection

Do not show raw JSON as the main Admin User experience.

## Testing Notes

Functional tests must cover:

- no selected order creates only drafts, never real records
- selected order creates update drafts scoped to that order
- model unavailable fails the whole run
- local parsing is visible in Agent Processing Trace
- no local risk fallback is generated when model fails
- only file upload defaults to data entry, not risk prompting
- missing required information keeps the retained conversation
- Minimal Goods Line Draft can be created from a goods name alone
- Master Data Draft shows possible duplicate risk
- deletion intent is recognized but not executable
- risk categories are model-driven and open-ended
- automated tests mock DeepSeek but verify model calls are required
- release/manual testing uses real DeepSeek API for the primary demo scenario and risk-prompt scenario

UI tests must cover:

- business workbench layout
- real processing trace visibility
- model success and failure display
- business summary plus collapsible raw response
- retained conversation after refresh
- missing-information prompt and later continuation
- full 1280px business-workbench usability
- scrollable conversation list
- scrollable Agent Processing Trace
- scrollable wide or long draft tables
- clear failure state that cannot be mistaken for success
- no jump to page top after button actions
- execution summary after confirmation without auto-navigation

## Phase 2 / Not MVP

Do not include these in MVP:

- image OCR for `.png`, `.jpg`, or chat screenshots
- automatic supplier-message sending
- supplier follow-up task system
- finance cost/charge drafts
- container or loading drafts
- Customs Goods Version drafts
- intelligent document generation
- multi-model switching
- automatic retry
- fallback model behavior
- user-configurable Agent orchestration
- cross-order automatic source filing
- delete-order or delete-Goods-Line drafts
- complex master-data merge flows
- long-term model logs or model cost dashboard
- new fine-grained non-Admin permission system
