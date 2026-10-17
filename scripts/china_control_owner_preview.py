"""Acquire exact comparison periods; private preview only, never Telegram/WB writes."""
import json,os,math
from datetime import datetime,timedelta,timezone
from urllib.parse import urlparse
from china_agent.morning_pair import PairWorker,tracked_rows
from china_agent import demand
from analytics.mpstats_primary import products
from analytics.mpstats_probe import discover
from analytics.mpstats_gaps import execute_reads
from analytics.mpstats_recovery import normalize
from advertising_agent.mpstats_economics import calculate

class Preview(PairWorker):
    def guard(self,session,method,url,*a,**kw):
        host=urlparse(url).hostname;path=urlparse(url).path
        if host not in ('mcp.mpstats.io',urlparse(os.environ['SUPABASE_URL']).hostname):
            raise RuntimeError('Preview network restricted to MPStats and storage')
        if host!='mcp.mpstats.io' and (('/rpc/' in path) or (method.upper() not in ('GET','HEAD') and path.rsplit('/',1)[-1] not in ('analytics_snapshots','telegram_api_cache'))):
            raise RuntimeError('Preview database write forbidden')
        return super().guard(session,method,url,*a,**kw)

    def acquire(self,windows):
        read=lambda t,p:self.db('GET',t,params=p)
        requests=[]
        for start,end in sorted(windows):
            rows,marker=products(read,'token_3',start,end,datetime.now(timezone.utc))
            if marker:continue
            requests.append(dict(cabinet='token_3',tool='lk_wb_products',key='china-control:'+start+':'+end,
                arguments=dict(date_from=start,date_to=end,start_row=0,end_row=1500),priority=90))
        if not requests:return
        pause=read('telegram_api_cache',dict(cache_key='eq.mpstats:cooldown',expires_at='gt.'+datetime.now(timezone.utc).isoformat(),select='cache_key',limit=1))
        if pause:raise RuntimeError('MPStats shared cooldown; preview not ready')
        def persist(cabinet,obs):
            args=obs['arguments']
            if cabinet!='token_3' or (args['date_from'],args['date_to']) not in windows or not obs.get('scope_verified'):
                raise RuntimeError('Control receipt scope mismatch')
            fields=dict(cabinet=cabinet,run_id='china-control-preview-'+os.environ['GITHUB_RUN_ID'],period_from=args['date_from'],period_to=args['date_to'],detail='Exact price control periods; owner preview only')
            self.db('POST','analytics_snapshots',body=dict(fields,source='mpstats_lk_wb_products',status='complete' if obs['status']=='received' else 'error',payload=[obs]))
            if obs['status']=='received':
                source,value=normalize(obs,cabinet)
                self.db('POST','analytics_snapshots',body=dict(fields,source=source,status='complete',payload=[value]))
            if obs.get('retry_after'):self.save('mpstats:cooldown',dict(pending=True),max(1,obs['retry_after'])/86400)
        def extra(call,checks,known):return execute_reads(call,checks,known,requests,{},persist,max_requests=len(requests))
        discover(os.environ['MPSTATS_API_TOKEN'],read_checks=True,extra_reader=extra)

    def build(self):
        state=self.get(demand.STATE_KEY) or {}
        tracked=tracked_rows(state,self.day)
        windows=set();cohorts={}
        for nm,e,c,d in tracked:
            n=min(4,max(0,(self.day-d).days-1))
            if not n:continue
            # First four days after detection, never a shifting window after assessment.
            end=min(self.day-timedelta(days=1),d+timedelta(days=4));start=d+timedelta(days=1)
            before_end=d-timedelta(days=1);before_start=before_end-timedelta(days=n-1)
            pair=((str(before_start),str(before_end)),(str(start),str(end)))
            windows.update(pair);cohorts[nm]=pair
        self.acquire(windows)
        read=lambda t,p:self.db('GET',t,params=p)
        costs=read('analytics_costs',dict(select='article,cost,observed_at,source',limit=5000)) or []
        own={r['article']:r['cost'] for r in costs if r.get('article') and r.get('cost') is not None}
        facts={};sources=[]
        for start,end in sorted(windows):
            rows,marker=products(read,'token_3',start,end,datetime.now(timezone.utc))
            if not marker:raise RuntimeError('Exact comparison receipt unavailable: '+start+':'+end)
            obs,=marker['payload'];economics=calculate(obs,own,start,end,tax_rate=0)
            grouped={}
            for r in rows:grouped.setdefault(str(r['nm_id']),[]).append(r)
            result={}
            for nm,variants in grouped.items():
                if len(variants)!=1:continue
                r=variants[0];views=r.get('open_card_count');fo=r.get('funnel_orders_count')
                result[nm]=dict(orders=r.get('orders_count'),views=views,funnel_orders=fo,
                    conversion=fo/views if type(views) in (int,float) and views>0 and type(fo) in (int,float) else None,
                    conversion_status='no_views' if views==0 and fo==0 else 'available' if views else 'missing',
                    profit=(economics.get(int(nm)) or {}).get('net_profit'),profit_status=(economics.get(int(nm)) or {}).get('economics_status','unverified_finance'))
            facts[(start,end)]=result;sources.append(dict(period_from=start,period_to=end,id=marker['id'],collected_at=marker['collected_at'],rows=len(rows)))
        out=[];gaps=[]
        for nm,e,c,d in tracked:
            item=dict(nm_id=nm,article=e.get('article',nm),detected_at=str(d),before_price=(c.get('before_price') or {}).get('current_cny'),after_price=(c.get('after_price') or {}).get('current_cny'),assessment_date=str(d+timedelta(days=5)))
            pair=cohorts.get(nm)
            if pair:
                for label,period in zip(('before','after'),pair):
                    v=facts[period].get(str(nm))
                    item[label]=dict(period_from=period[0],period_to=period[1],**(v or {}))
                    missing=['orders','profit']+([] if v and v.get('conversion_status')=='no_views' else ['conversion'])
                    absent=[k for k in missing if v is None or v.get(k) is None]
                    if absent:gaps.append(dict(article=item['article'],nm_id=nm,period=list(period),missing=absent,reason=(v or {}).get('profit_status','absent_product')))
            out.append(item)
        value=dict(report_date=str(self.day),status='complete' if not gaps else 'incomplete',products=out,gaps=gaps,sources=sources,wb_writes=0,telegram_calls=0)
        self.save('china_agent:control_owner_preview:'+str(self.day),value)
        print(json.dumps(dict(status=value['status'],products=len(out),gaps=len(gaps),sources=sources,wb_writes=0,telegram_calls=0)))

if __name__=='__main__':
    w=Preview('control')
    try:w.build()
    finally:
        import requests
        requests.sessions.Session.request=w.original_http
