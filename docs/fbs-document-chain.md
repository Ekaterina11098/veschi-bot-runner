# China FBS document chain — prepared 2026-10-20

User-approved process: new WB supply delivery transition -> one customer order on Moscow stock -> posted demand -> posted full sales return to Hong Kong WB FBO. All position prices are zero. Only China token_3; WB is read-only. Historical supplies must not be backfilled.

Implementation: scripts/fbs_document_chain.py; workflow fbs-document-chain.yml.
Secrets: existing WB_TOKEN_3, MOYSKLAD_API_TOKEN, SUPABASE_URL, SUPABASE_SECRET_KEY. Secret values never leave the runner.
Private configuration: public.telegram_api_cache key fbs_document_chain:china:config:v1. Per-supply journals use fbs_document_chain:china:supply:v1:<supply ID>.
Configuration templates were copied from the existing complete China chain WB-GI-295600580. Its organization is IP Lazarev Viktor Alekseevich, while its buyer is OOO Wildberries. This distinction needs acknowledgement during verification. Actual target warehouse name is Гонконг WB FBO.

## Current state
Prepared and paused: writes_enabled=false, status=configured_pending_verification, scope_confirmed=false.
Scheduled jobs additionally require repository variable FBS_DOC_CHAIN_ENABLED=true. Do not set this until verification is complete.
The one-time read-only inspection workflow is separate and has no schedule.
No live document chain test or creation has been executed by this automation.

## Verification and activation, deferred at user's request
1. Confirm organization versus buyer from the existing chain; set scope_confirmed=true only after resolving the user's intent.
2. Run status, then preview through workflow_dispatch. Preview reads one recent supply, validates complete order matching and exact articles, retains the report privately, and creates no MoySklad documents.
3. Run bootstrap once at the agreed activation moment. It saves the timestamp and all currently closed supplies as the baseline. It creates no operational documents and cannot overwrite an existing baseline.
4. Enable writes_enabled=true and status=active in private configuration and enable FBS_DOC_CHAIN_ENABLED. Run one new real supply under supervision, then verify all three posted documents and actual stock movement. Work is not proven until this live verification.
5. Schedule polls every five minutes; GitHub queue delays can increase latency.

## Recovery
Before each document creation, persist an inflight marker. Each document has deterministic externalCode fbs-china:<supply ID>:<document type>. Each next stage requires successful readback of organization, buyer, warehouse, zero sum, posted state, links and all quantities.
If the response to a write is uncertain and no matching document is found, do not blindly retry: the marker blocks another create until manual reconciliation. Earlier stages must never clear a later stage's uncertain marker.
Existing manual customer order with the same supply number stops creation for reconciliation.
Unknown or duplicate articles, products with variants or marking/serial requirements stop that supply for configuration; do not substitute a similar product.
Supply composition changes stop processing. No deletion, price changes, WB status changes or stock publishing are performed.
Pause by clearing writes_enabled first and disabling FBS_DOC_CHAIN_ENABLED. Retain baseline and journals; do not erase them to retry.
