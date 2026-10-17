# Prepared daily advertising repair — separate deployment approval required

This patch changes the existing dedicated advertising process only.
- Analysis, delivery receipts, and budget evidence have independent statuses. Zero messages never imply accepted recommendation quality.
- Pending budget IDs and next_allowed_at are durably saved and fully read back before another WB GET. Existing 905-second and Retry-After controls remain owned by the same collector.
- Budget-only continuation requires the exact terminal day/run/attempt and a saved analysis stage; it skips sources, order ingestion, membership collection, analysis and delivery. The profile stays disabled.
- The budget worker has independent request and wall-time caps. It preserves pending work on429, expiration or deadline; it does not start another worker. Membership older than6hours is not bypassed.
- Stage HTTP records are saved before requests and after responses/errors, then merged into the same CAS-protected day claim. Attempt, stage and pass totals are separate and idempotent. Earlier unmeasured history remains explicitly incomplete.
- Full source/budget receipts and checkpoints have stage/attempt names so a later stage cannot overwrite them.
- The unchanged100000000 decoded-response-byte guard spans the current pass, with durability and limited cabinet cleanup allowed. Request bodies are counted separately; wire bytes remain unknown.
-07:30MSK cron/private analytics pin and all WB mutation/forecast/test restrictions are unchanged. No periodic wakeups, executable test jobs, or new advertising schedules are enabled.
- Observed inactive membership makes old test drafts require review; it never authorizes resuming campaigns or treats a pause as an agent experiment.
- Real continuation of the saved incomplete day is a separate owner decision after deployment; this PR does not arm its profile.
