# AI资料收集箱 Phase 2

## Trigger

Start this phase after the MVP proves that Admin Users repeatedly use `AI资料收集箱` to process supplier package data, resolve conflicts, and batch import safe fields.

## Add Next

- Better PDF extraction after real supplier document samples are known.
- Saved source templates for recurring supplier Excel formats.
- Higher-confidence matching rules per customer item number, SKU, product URL, and supplier-specific naming patterns.
- More safe-field categories after approval history proves they are low-risk.
- Supplier message templates with tone and language variants.
- Optional email/WeChat copy helpers, still without automatic sending.
- AI cost dashboard if model usage becomes meaningful enough to manage.
- Prompt management UI only if non-developers need to tune prompts safely.

## Keep

- Import Order remains the required starting context.
- `AI资料收集箱` remains an intake inbox, not a generic chat assistant.
- Official documents still require Admin User confirmation.
- Unsafe fields remain human decisions.
- Supplier messages are drafts until an Admin User sends them outside the system.

## Do Not Add Yet

- Autonomous order changes.
- Automatic supplier messaging.
- AI-created Supplier, Customer/Consignee, Warehouse, or Company/System master data.
- Live carrier, customs, or government certificate integrations.
- User-configurable agent orchestration.
