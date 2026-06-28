# CargoPilot Order Assistant PRD

## Goal

Add an order-centered AI assistant that helps Admin Users review one Import Order, find risks, prepare structured data, and create drafts that still require administrator confirmation.

The MVP uses a fixed multi-agent workflow: a Router chooses the needed specialist agents, specialist agents produce structured findings, and a Coordinator merges them into Review Requests.

The reason to use agents is not to add a generic AI platform. Agents exist to isolate complex-task decomposition, permissions, context, tools, output formats, and responsibility boundaries.

## Product Shape

The MVP has one **Order Assistant** entry for the selected Import Order. Business workflow sections also expose contextual AI buttons:

- `订单详情`: AI检查订单
- `货物详情`: AI检查货物资料
- `海运单证`: AI检查单证阻塞项 and AI生成单证草稿
- `成本利润`: AI检查利润风险
- `Dashboard`: risk links open the relevant Import Order assistant result

The Order Assistant entry lives inside the selected Import Order detail in `订单详情`; it is not a new left-navigation section in the MVP.

Contextual buttons show results in the current section drawer and also save them to the Order Assistant entry for that Import Order.

## MVP Boundary

Build first:

- Order Assistant entry tied to one selected Import Order.
- Assistant Suggestion list with three levels: suggestion, review-needed, blocking-risk.
- Assistant Suggestions attached to the selected Import Order or affected Goods Lines.
- Review Request flow for Admin Users.
- Change Draft flow after administrator approval.
- Fixed multi-agent workflow with Router, specialist agents, and Coordinator.
- Router based on task templates plus source rules.
- Agent isolation standard covering task, permission, context, tool, output, and responsibility boundaries.
- DeepSeek model API integration for low-cost demos.
- File and text intake for fixed practical sources: Excel, PDF, and pasted chat records.
- Assistant output audit storing input summary, output suggestions, cited sources, and administrator handling result.
- Administrator confirmation before sending real customer data to an external model API.
- Background assistant runs that keep the current workflow page usable while checks are running.
- Model usage logging with model name, run time, token counts, and selected Import Order.
- Structured JSON output from model calls.

Skip for MVP:

- Direct AI application of changes.
- AI-generated official documents without administrator confirmation.
- One-click applying all drafts.
- General-purpose agent orchestration or open-ended autonomous planning.
- Arbitrary spreadsheet recognition beyond the assistant's best-effort extraction draft.
- AI changes to Order Status, warehouse receiving results, or loading records.
- AI-created Supplier, Customer/Consignee, Warehouse, or Company/System master-data drafts.
- Configurable profit-risk thresholds.
- AI cost dashboard.
- Prompt management UI.
- Configurable routing UI.

## Module Index

- [Order Assistant MVP](./modules/order-assistant.md)
- [Order Assistant Phase 2](./modules/order-assistant-phase-2.md)
- [Order Assistant Development Plan](./order-assistant-development-plan.md)

## Phase Signal

MVP is complete when the assistant can route an Import Order task through the needed specialist agents, produce useful suggestions, request administrator review, and prepare Change Drafts that can be individually confirmed.

Phase 2 starts only after MVP users repeatedly accept similar low-risk Change Drafts and ask to reduce repeated confirmation work.
