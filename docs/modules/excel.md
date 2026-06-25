# Excel Import and Export Module

## Scope

Support fixed-header Excel imports and useful Excel exports.

## Imports

Customer purchase-list headers:
order_no, supplier_name, customer_item_no, product_url, cn_name, en_name, customs_en_name, sku_or_model, category, hs_code, quantity, unit, target_markup, sales_unit_price, sales_currency, notes.

Supplier package/logistics headers:
order_no, supplier_name, sku_or_model, customs_en_name, carton_count, units_per_carton, carton_length_cm, carton_width_cm, carton_height_cm, carton_gross_weight_kg, domestic_tracking_no, shipping_mark, purchase_unit_price, purchase_currency, supplier_invoice_no, notes.

## Exports

Export Import Orders, Goods Lines, dashboard filtered results, cost/profit reports, warehouse receiving lists, and loading lists.

## Out of Scope

Smart recognition of arbitrary spreadsheet formats.

## Test Focus

- Required headers.
- Row validation.
- Update existing Goods Lines from supplier package/logistics imports.
- Export column shape.
