"""Pure regression on immutable morning source. No API, intents, reports or replay."""
import json,time
import tg_agent_new as g
from stock_deploy_support import runtime_db,seal
from stock_operation_store import Store,canonical,digest,Stopped
from stock_physical_pool_routing import msk_view,routes
ROOT='technical:china-mgt-routing-regression:2026-11-11'
def forbidden(*args,**kwargs):raise AssertionError('No marketplace/MS API permitted in pure routing regression')
g.api=forbidden
with runtime_db() as db:
 store=Store(db,postgres=True)
 raw=store.sql('SELECT snapshot FROM stock_runs WHERE id=?',('technical:stock-daily:2026-11-11:0700',)).fetchone()
 original=json.loads(raw[0]);source=original['source'];original_digest=digest(source)
 filtered=msk_view(g,source);assigned=set(routes()['articles']);evidence=filtered.get('physical_pool_routing',{})
 if set(evidence.get('articles',[]))!=assigned:raise Stopped('Real saved source did not route all18 exact identities')
 if assigned&set(filtered['moscow_raw']) or any(assigned&set(s) for s in filtered['fbs']):raise Stopped('China-only identity still in MSK candidates')
 if digest(source)!=original_digest:raise Stopped('Historical source mutated')
 if {a:q for a,q in filtered['moscow_raw'].items()}!={a:q for a,q in source['moscow_raw'].items() if a not in assigned}:raise Stopped('Other MSK source quantities changed')
 result=dict(complete=True,pure_saved_source_regression=True,marketplace_calls=0,stock_writes=0,ms_document_writes=0,telegram_messages=0,assigned_count=len(assigned),routing=evidence,retained_other_msk_articles=len(filtered['moscow_raw']),historical_source_digest_unchanged=original_digest,finished_at=time.time())
 with store.transaction():store.sql('INSERT INTO stock_runs VALUES(?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET snapshot=excluded.snapshot',(ROOT,canonical(result),'{}',digest({}),'technical-no-executor',time.time()))
 seal('mgt-routing-regression',result);print(json.dumps(dict(complete=True,routed=18,marketplace_calls=0)))

