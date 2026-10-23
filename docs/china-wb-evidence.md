# China WB evidence, 23 October 2026

Official contracts: https://dev.wildberries.ru/docs/openapi/analytics and https://dev.wildberries.ru/docs/openapi/documents-and-accounting .

The China token successfully reads all-source sales-funnel statistics for all300 catalogue products. Its actual selected/past response contains openCount, cartCount, orderCount and orderSum. openCount is card openings/clicks, never impressions. The documented standard products/history/CSV output does not provide a total-impressions field. Do not claim that all-source or organic impressions are connected. Do not extract browser credentials or scrape a hidden private API to fill this gap.

WB wins for the same metric/cabinet/period. WB created orders, WB funnel attribution, MPStats counters and ad attribution retain their distinct definitions. Daily funnel updates can lag2 hours; today's snapshot is not a matched-clock comparison to yesterday.

Finance reads the current sales-reports/detailed endpoint, using the existing China Finance credential after checking seller identity. Commercial responses and cursors stay in private cache. Only HTTP204 closes pagination; short200 is not complete. Published operation dates and createDate are preserved. Publication absence is not zero activity, and later adjustments remain possible.

Finance CNY and Chinese operation names are validated. Returns reverse the signed seller payout. forPay already includes commission: never subtract it or acquiring again. WB Promotion deductions already in settlement are not subtracted again as advertising statistics. Cabinet charges are not silently allocated to SKUs.

Owner-approved inputs: tax5% on signed seller-price revenue after seller discount, before WB discount; own current MoySklad COGS, RUB/CNY12 as the existing explicit calculation assumption. The resulting total profit is calculated/preliminary, not a filed tax result or immutable historical closed cohort. Historical COGS, external return-to-RF and other unverified costs remain visible limitations, not fabricated zeros. Costs are collected automatically from MoySklad; their mere absence from the first WB response is not a blocker.

The model can request get_wb_evidence for exact dates/SKUs; decline diagnostics include primary WB clicks/conversion plus cabinet/day/SKU published-operation results. Existing morning/backups cache the same read sources; no new schedule. No WB mutations, executable plans, credential/access changes, or Telegram sends are added by this collector.
