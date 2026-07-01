# CargoPilot 订单智能体 PRD

## Goal

Add a polished `订单智能体` Workflow Section that demonstrates how CargoPilot turns real order operations into controlled Agent workflows. The MVP focuses on two business goals:

- 资料录入: create or update order data from natural-language instructions and uploaded materials.
- 风险提示: use a live model to identify order-level customs, document, compliance, or workflow risks.

`AI资料收集箱` remains available as the fallback demo path during development. Do not delete or replace it in this MVP.

## Product Shape

`订单智能体` is a first-level Admin workflow section placed above `AI资料收集箱`.

The UI is a business workbench, not a pure chat window:

- retained conversation list
- optional Import Order selector
- upload control and natural-language input
- Agent Processing Trace
- business conclusions
- editable draft forms
- risk suggestions
- missing-information prompts
- execution summary

Every meaningful process step must be visible, including local attachment parsing, model calls, model success or failure, downstream Agent selection, generated outputs, and blocked steps.

## MVP Agents

The MVP uses exactly three live-model Agents:

- Task Understanding Agent / 任务理解 Agent
- Data Entry Agent / 资料录入 Agent
- Order Risk Agent / 风险提示 Agent

Task Understanding decides whether data entry, risk prompting, both, or neither should run. Data Entry and Risk Prompting require successful live model responses. Local parsing may prepare attachment summaries, but must not generate user-facing draft applications or risk findings when the model fails.

## Primary Demo Scenario

Use this as the interview demonstration path:

```text
No Import Order selected
→ upload supplier material or paste chat records
→ enter: "帮我根据这些资料创建一个订单"
→ Trace shows local parsing, Task Understanding, Data Entry, and missing information
→ user adds: "目的港 Rotterdam，客户 Eldar"
→ Agent merges the conversation
→ user reviews Order Creation Draft, Goods Line Drafts, Supplier / Consignee drafts
→ user confirms execution
→ UI shows a creation summary without auto-navigation
```

## Secondary Demo Scenario

```text
Existing Import Order selected
→ enter: "帮我检查这个订单清关和单证风险"
→ Task Understanding selects risk prompting only
→ Order Risk Agent calls the live model
→ UI shows supplier-grouped risks, basis, affected goods, suggested documents/actions, confidence, and raw structured response in collapsed details
```

## Confirmation Model

All writes require administrator confirmation. The MVP uses a two-step chain:

```text
AI 建议
→ 待确认草稿
→ 确认执行
```

After execution, stay in `订单智能体` and show a concise summary. Do not auto-jump to `订单详情`, and do not add a special "open order" flow in MVP.

## Scope

Build:

- retained conversations
- multi-file input batch
- Excel/PDF/TXT/pasted-text input
- PDF OCR
- live model required failure behavior
- Task Understanding, Data Entry, and Order Risk model calls
- Order Creation Draft
- Order Update Draft
- Minimal Goods Line Draft
- Supplier / Consignee create-or-reuse drafts
- duplicate-risk display for master data
- editable draft forms before confirmation
- supplier-grouped risk suggestions
- processing trace with business summary and collapsible raw structured response
- manual retry of failed step

Skip:

- image OCR
- automatic supplier messaging
- supplier follow-up workflow
- finance drafts
- container/loading drafts
- Customs Goods Version drafts
- intelligent document generation
- multi-model switching or fallback models
- configurable Agent orchestration
- cross-order automatic filing
- delete drafts
- complex master-data merge
- long-term model logs or cost dashboard
- new fine-grained permissions

## Source Docs

- [订单智能体 MVP Module](./modules/order-agent.md)
- [Order Agent Can Start Without an Import Order](./adr/0005-order-agent-can-start-without-order.md)
- [Order Agent Uses Retained Conversations](./adr/0006-order-agent-uses-retained-conversations.md)
- [Order Agent Requires a Live Model](./adr/0007-order-agent-requires-live-model.md)
