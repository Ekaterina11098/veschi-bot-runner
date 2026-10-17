# Daily advertising source repair — prepared, not activated

The 17 October run39004453781 stopped in source. Four order observations17841–17844 and finance17845/17847/17849/17851 plus catalog17853 are retained. The observer ingestion is not replayed.

## Scope

- Keep100000000 decoded HTTP-body bytes as the collection threshold. It is neither compressed network traffic nor post-storage JSON expansion. Record counters and safe per-host/table/tool buckets even after exceptions.
- Do not block durable writes/readbacks or at most two cabinet-restoration calls because the collection threshold has been reached. No extra report tool is allowed through that exception.
- Load derived report/funnel caches once, apply updates in memory, flush once with CAS and full readback. Raw snapshots, normalized snapshots and observer state remain immediately durable. No history is deleted.
- Reconcile the exact9retained receipts into derived caches; never recollect or reingest the4successful order observations. Validate all identities before reconciliation, reuse existing normalized snapshot IDs.
- Deduplicate planned request keys; retain exact unfinished requests. Read only missing/stale dates under existing limits and cooldowns.
- Resume only the exact terminal incomplete same-day claim39004453781:1 via CAS; do not delete/reset the claim or steal a running run. Existing complete checkpoints and delivery are skipped. The provided profile remains enabled=false.
- Record complete/incomplete/failed, reason, completed/pending stages and analysis_complete. Incomplete/failed exits nonzero in the actual daily job; ciphertext upload still runs always. Unknown budgets do not stop independent analysis.
- Preserve the existing delivery ledger, RetryAfter, uncertain-delivery no-replay rule and one reminder per Moscow day. No old queue is enabled.

## Measured evidence and limits

GET-only diagnostics39013476298 and39014102317 made no MPStats/WB/Telegram calls or business DB writes.
Retained compact JSON: order responses25292bytes; four daily finance responses4428147bytes; catalog56208bytes. Total4509647bytes.
Derived report index476214bytes compact JSON; actual HTTP decoded response521365bytes.
Funnel cache7891583bytes compact JSON,34175period entries/380SKUs; actual HTTP decoded response8334794bytes.
At the measured final cache size,8old funnel reads imply66678352decoded bytes;2new reads imply16669588bytes, a50008764byte reduction. This is a reconstruction using the retained final version, not an exact byte log of the old growing cache. HTTP gzip was present; decoded sizes are not billed compressed egress.
The original exception receipt omitted traffic, so original exact per-stage HTTP totals and compressed network volume are unknown. The cutoff happened after catalog stats page0, before the next MPStats state call; cleanup was blocked by the same guard. There is no evidence to increase the threshold.

## Approval and continuation

No merge or business continuation is performed by this preparation. PR28/runner6 remain untouched and unmerged.
One approval may cover this narrow runner repair, keeping07:30MSK cron/private analytical pin unchanged, and one controlled17October continuation by enabling the exact reviewed profile and changing the existing controlled trigger.
Before actual continuation: verify no competing source/budget writer; retain the shared writer lock and any live RetryAfter. Finish remaining catalog pages for stats/state, only needed campaign-day/product slices and finance recomposition from latest saved daily versions. Then membership, permitted single budget step, analysis/new notifications/reminders and same-writer budget completion. Do not independently refresh the complete13balance set.
Do not replay the4order observations or the4finance/provider page already received. Independent observer requests may run only if due under the existing24h/7d rules.
The first attempt may still identify a bounded pending source scope; report it explicitly instead of green success. No automatic unbounded retries.

Stocks/reviews/China schedules unchanged. WB mutations, real experiments, forecasts and general dispatcher remain off.
