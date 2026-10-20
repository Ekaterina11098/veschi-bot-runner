# FBS document chains — approved configuration, 2026-10-20

Organization: ИП Лазарев Виктор Алексеевич.
Every chain is one posted customer order on МСК -> one posted demand on МСК -> one posted full sales return on the configured marketplace warehouse. All position prices, discounts and document sums are zero. Customer order completion state is Возврат на ФБО, set after the full return is verified.

| Cabinet | API credential | Buyer | Return warehouse |
| --- | --- | --- | --- |
| WB China | WB_TOKEN_3 | ООО "Вайлдберис" | Гонконг WB FBO |
| WB IP | WB_TOKEN_2 | ООО "Вайлдберис" | Склад WB FBO |
| WB OOO | WB_TOKEN_1 | ООО "Вайлдберис" | Киргизия WB FBO |
| Ozon | Existing Supabase OZON_CLIENT_ID / OZON_API_KEY | ООО."Интернет решения" | Склад OZON |

## WB
Trigger: a new supply delivery transition (done=true, closedAt). One supply is one chain. Order name is the exact WB-GI supply ID. Comments are identical on all three documents: shipment date in Moscow, cabinet label and supply category. Example: 20 10 26  Гонконг Сумки.
Raw supply order IDs are not a picking list quantity: canceled / canceled_by_client orders and supplier-canceled orders are excluded before document creation. Exact included and excluded IDs, articles and statuses are retained privately. Product matching uses a complete active product catalogue, case-insensitive exact articles and uniqueness checks. Unknown or duplicate articles, variants and marking/serial requirements block the chain for reconciliation.
User reported 221 in the WB cabinet but 220 in the picking list for WB-GI-296250890. API identified canceled order 6071589005, article 534-NoelBag-emerald, one unit. The original order, demand 02740 and return 02440 were corrected and independently read back as 220 posted units each. Original source and repair proof remain in the private journal.

## Ozon
Trigger: the non-canceled postings of one act move to delivering (delivered is accepted for catch-up after an observed new transition). Act formation / awaiting_deliver never triggers stock movement.
One act/list is one chain; acts are never merged by date.
Order name is the act shipment date DDMMYY, for example 201026.
The identical comment on all three documents contains every included posting number, comma-separated.
Canceled-before-shipping postings are excluded. Cancellations explicitly marked as after shipping retain physically shipped goods.
Act/posting products and quantities must agree; partial/split acts and ambiguous data stop for reconciliation.

## Runtime and state
Workflow .github/workflows/fbs-document-chain.yml polls every five minutes, subject to GitHub scheduling/queue delays. It processes the three WB cabinets with isolated state and attempts Ozon independently even if a WB worker fails.
Shared stock concurrency prevents conflicting runs.
Private state is in existing RLS-protected public.telegram_api_cache, under fbs_document_chain:<china|ip|ooo|ozon>: keys. Configuration and baseline are separate. No historical backfill is authorized, except the three exact WB pilots requested by the user.
China retains its original operational activation boundary, including work arriving during the temporary reconciliation pause. IP, OOO and Ozon have individual verified baselines. Already delivered old supplies/acts are excluded. Ozon acts still awaiting shipment at setup are watched for a later delivery transition.
writes_enabled and status=active are required for a cabinet to create documents. Pause a cabinet by setting writes_enabled=false; never erase its baseline or journal to retry.

## Recovery and verification
Deterministic externalCode plus per-source journals prevent repeat creation. An inflight marker is saved before every create; an uncertain write with no matching document blocks blind retry.
Each stage is read back for posted state, zero prices/sum, quantities, organization, buyer, warehouse, comment and parent links.
An order already entered manually for the same source stops creation for reconciliation.
Existing verified documents are reused, not recreated. Source composition drift after a partial chain stops further execution.
The three China pilots passed live API verification and idempotent reruns; the last was subsequently reconciled to the user's 220-unit picking list.
Twenty-four offline checks cover shared chain behavior, comments, status timing, article case/ambiguity, 221 raw minus one cancellation equals 220 picked, Ozon shipment-date naming, delivery readiness and cancellation timing.
Ozon live preview verified act 124091131: order name 201026, three postings, three units, all exact articles matched. It was awaiting shipment, so no Ozon documents were created during setup.

## Credentials
WB and MoySklad credentials remain in existing GitHub secrets.
Ozon credentials remain in Supabase. fbs-ozon-read authenticates an existing backend Supabase key and allows only act list, act postings and posting detail reads. It cannot mutate Ozon. No provider credential values are returned or logged.

## Continuous comment reconciliation
Every regular run independently audits up to ten completed, ledger-owned chains across all four cabinets, with a persistent round-robin cursor. New chains already require matching comments on all three documents before completion. The audit also restores comments removed or changed later from the recorded approved comment. It verifies scope, parent links, zero prices, posting and original quantities before writing only description, then reads back and verifies each document. Manual/untracked documents are outside this scope. Full on-demand inspection uses scripts/fbs_comment_audit.py --all. Private audit results are in fbs_document_chain:comment_audit:last_run:v1. First pilot demand 02738 and return 02438 were repaired to 20 10 26  Гонконг Зонты with 17 units unchanged.
