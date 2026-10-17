import json,os
from stock_deploy_support import runtime_db,seal,error
ARTICLES=['158-BonnieBag-brown','64-Zont-cream-beige','91-Zont-yellow','121-Zont-beige','79-Zont-yellow']
try:
    with runtime_db() as db:
        db.execute("SET TRANSACTION READ ONLY")
        rows=db.execute("""
          WITH runs AS (
            SELECT id,snapshot::jsonb AS j FROM stock_runs
            WHERE id LIKE 'technical:stock-daily:2026-10-17%'
            ORDER BY id DESC LIMIT 8
          )
          SELECT id,j->>'status',coalesce(j->'source',j->'source_snapshot')->'received_at',
             (SELECT jsonb_object_agg(a,coalesce(j->'source',j->'source_snapshot')->'moscow_raw'->a)
                FROM unnest(%s::text[]) a),
             (SELECT jsonb_agg(c) FROM jsonb_array_elements(coalesce(j->'source',j->'source_snapshot')->'cards'->1) c
                WHERE c->>'vendorCode'=ANY(%s::text[])),
             (SELECT jsonb_object_agg(a,coalesce(j->'source',j->'source_snapshot')->'fbs'->1->a)
                FROM unnest(%s::text[]) a)
          FROM runs
        """,(ARTICLES,ARTICLES,ARTICLES)).fetchall()
        result={'read_only':True,'source_calls':0,'wb_writes':0,'telegram_calls':0,'articles':ARTICLES,
                'runs':[dict(zip(['run','status','observed_epoch','moscow','ip_cards','ip_fbs'],r)) for r in rows]}
        raw=json.dumps(result,default=str).encode()
        assert len(raw)<1000000
        result['response_bytes']=len(raw)
    seal('growth-retained-stock',result)
    print({'saved_rows':len(rows),'response_bytes':len(raw),'source_calls':0,'writes':0})
except Exception as exc:
    seal('growth-retained-stock',{'error':error(exc),'read_only':True,'source_calls':0})
    raise
