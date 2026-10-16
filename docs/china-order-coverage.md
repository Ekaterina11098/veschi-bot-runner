# China price report: complete order coverage
Updated 2026-10-16 for the owner's instruction to obtain order data for all catalogue products.

The 10:30 Moscow pair and the 15:00 Moscow report retain their existing schedules, delivery IDs and source commit. These changes allow data reads and recommendations only. No prices, discounts, advertising, inventory or reviews are changed.

## Source order
1. Read the exact completed-day MPStats products receipt and compare its nmIDs with the China price catalogue.
2. For omitted cards, obtain a scoped show_all comparison to identify the internal product_id. Read card orders for the exact period; validate the product filter, dates, pagination count and row identities. Reconcile with the expanded table's order total when present.
3. Cards absent from the expanded MPStats catalogue use a narrow WB order-only fallback, authorized by the owner's all-products data request on 16 October. This does not change the global MPStats-first policy. Check the China seller sid, read flag=1 for each missing completed Moscow day, validate every row's date, srid, cancellation state and identity, and reuse the saved daily receipts. WB Statistics is preliminary and may omit unconfirmed payments.
4. Retain missing or ambiguous evidence as unknown. A failed request, absent mapping or omitted product does not establish zero orders.

Original raw receipts and the coverage result are retained with source snapshot IDs. Completed-day receipts must have been collected after the day closed. Respect the existing shared MPStats lock and WB cooldown/Retry-After.

## Separation of measures
Supplemented order histories participate in the order-per-day criterion. They do not create sales, returns, revenue, profit, funnel events or conversion. Unknown buyouts remain null, including during candidate sorting and selection of products for other data sources. The own-profit formula and funnel conversion remain unchanged.

The morning report is freshly recalculated rather than reusing the fixed 16 October job text. Price-change control remains the second morning message. Intraday selection receives order projections only; today's orders still come from its existing WB reader.

## Evidence for 12–15 October
The main MPStats receipt covered 298 products. Individual MPStats card reads confirmed zero daily orders for 13 omitted products. Two cards absent from the expanded MPStats catalogue (145-FlorenceBag-black and 482-RiginaBag-red) were checked using completed-day WB receipts. Their daily orders were zero as well. Order coverage is 313/313; this is not a claim of complete financial or conversion data.

Recovery runs:
- https://github.com/Ekaterina11098/veschi-bot-runner/actions/runs/38906270647
- https://github.com/Ekaterina11098/veschi-bot-runner/actions/runs/38906761921

## Verified integration
https://github.com/Ekaterina11098/veschi-bot-runner/actions/runs/38907252430

Five receipt-validation tests passed. Morning preview: 313/313 assessed, missing_sales_count=0. Intraday preview: missing=[], errors=[], complete coverage of 313 products. The morning control message also passed preview. Telegram deliveries were empty and WB writes were zero. Existing report schedules and source pins were retained.
