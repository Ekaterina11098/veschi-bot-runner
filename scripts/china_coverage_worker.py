"""Order coverage integration limited to the two China price reports."""
import argparse,copy,json,os
from contextlib import contextmanager
from datetime import date,datetime,timedelta
from urllib.parse import urlparse
from china_agent.scheduled_price_worker import ScheduledWorker
from china_agent.order_coverage import recover,KEY
from china_agent.wb_order_gaps import supplement

def overlay(report,coverage):
    """Supplement order criteria without inventing sales, conversion, or profit."""
    if (report.get('cabinet')!='token_3' or coverage.get('cabinet')!='token_3'
            or report.get('date_from')!=coverage.get('period_from') or report.get('date_to')!=coverage.get('period_to')):
        return report
    result=copy.deepcopy(report)
    start=date.fromisoformat(report['date_from']);end=date.fromisoformat(report['date_to'])
    for nm,item in coverage.get('products',{}).items():
        if (nm in result.get('products',{}) or item.get('status')!='complete'
                or item.get('period_from')!=str(start) or item.get('period_to')!=str(end)):
            continue
        values=item.get('orders_each_day')
        if (not isinstance(values,list) or len(values)!=(end-start).days+1
                or any(type(v) is not int or v<0 for v in values) or sum(values)!=item.get('orders')):
            continue
        result.setdefault('products',{})[nm]=dict(article=item['article'],nm_id=nm,orders=item['orders'],
                cancelled_orders=item.get('cancelled_orders'),order_days=[str(start+timedelta(days=i)) for i,v in enumerate(values) for _ in range(v)],
                sales=None,returns=None,sales_rub=None,returns_rub=None,net_sales=None,net_turnover_rub=None,
                sale_days=None,source=item['source'],order_coverage_only=True,financial_data_complete=False)
    result['order_supplement']=dict(status=coverage['status'],products=len(coverage.get('products',{})),
            catalogue=coverage['catalogue_count'],remaining=coverage.get('remaining',{}),financial_totals_unchanged=True)
    return result

class CoverageWorker(ScheduledWorker):
    def guard(self,session,method,url,*a,**kw):
        host=urlparse(url).hostname;path=urlparse(url).path;params=kw.get('params') or {}
        if host=='api.telegram.org' and path.endswith('/sendMessage'):
            body=kw.get('json') or {}
            text=body.get('text','')
            from china_agent.price_brief import table_payload,plain_payload
            catalogue=self.get('china_agent:prices:v1')
            table=plain_payload(text,catalogue) or table_payload(text,catalogue)
            if table:
                body=dict(body)
                body.pop('parse_mode',None)
                body.update(table)
                kw=dict(kw,json=body)
            elif text.startswith('Рекомендации к повышению:') or text.startswith('Рекомендации к снижению:'):
                from china_agent.price_brief import article_entities
                body=dict(body)
                body.pop('parse_mode',None)
                body['entities']=article_entities(text)
                kw=dict(kw,json=body)

        # Dedicated, read-only absent-card exceptions; the shared source policy is unchanged.
        if host=='mcp.mpstats.io':
            body=kw.get('json') or {};p=body.get('params') or {};args=p.get('arguments') or {}
            if body.get('method')=='tools/call' and p.get('name') in ('lk_wb_reports_compare','lk_wb_card_orders'):
                return self.original_http(session,method,url,*a,**kw)
        if host=='statistics-api.wildberries.ru' and path=='/api/v1/supplier/orders' and method.upper()=='GET':
            start=str(self.day-timedelta(days=4));end=str(self.day-timedelta(days=1))
            if params.get('flag')==1 and set(params)=={'flag','dateFrom'} and start<=params['dateFrom']<=end:
                self.audit['wb_historical_order_requests']=self.audit.get('wb_historical_order_requests',0)+1
                return self.original_http(session,method,url,*a,**kw)
        return super().guard(session,method,url,*a,**kw)

    def coverage(self):
        if hasattr(self,'_order_coverage'):
            return self._order_coverage
        prices=self.get('china_agent:prices:v1') or {}
        if prices.get('cabinet')!='token_3' or not prices.get('rows'):
            raise RuntimeError('China catalogue needed for order coverage')
        end=self.day-timedelta(days=1);start=end-timedelta(days=3)
        result=recover(self.db,self.get,self.save,start,end,prices['rows'])
        if result.get('remaining'):
            result=supplement(self.db,self.get,self.save,start,end,wait=True)
        self._order_coverage=result
        self.audit['order_coverage']={k:result.get(k) for k in ('status','catalogue_count','primary_product_count','remaining')}
        self.audit['order_coverage']['supplemented']=len(result['products'])
        return result

    @contextmanager
    def covered_sales(self):
        from china_agent import demand
        base=demand.sales_report;old_candidates=demand.candidates
        def sales(data,cabinet,date_from=None,date_to=None,now=None):
            report=base(data,cabinet,date_from,date_to,now)
            expected_start=str(self.day-timedelta(days=4));expected_end=str(self.day-timedelta(days=1))
            if cabinet=='token_3' and report.get('date_from')==expected_start and report.get('date_to')==expected_end:
                return overlay(report,self.coverage())
            return report
        def candidates(report):
            if not report['available']:return []
            wanted=demand.days(date.fromisoformat(report['date_to'])-timedelta(days=3),date.fromisoformat(report['date_to']))
            return sorted([p for p in report['products'].values() if all(p['order_days'].count(day)>=1 for day in wanted)],
                    key=lambda p:(p.get('sales') is not None,p.get('sales') or 0,p['orders']),reverse=True)
        demand.sales_report=sales;demand.candidates=candidates
        try:yield
        finally:demand.sales_report=base;demand.candidates=old_candidates

    def completed_products(self):
        rows,marker=super().completed_products()
        coverage=self.coverage();have={str(r['nm_id']) for r in rows}
        result=list(rows)
        for nm,item in coverage.get('products',{}).items():
            if nm not in have and item.get('status')=='complete':
                result.append(dict(nm_id=nm,sa_name=item['article'],orders_count=item['orders'],
                            sparkline_orders=item['orders_each_day'],source=item['source'],order_coverage_only=True))
        return result,marker

    def prepare(self,preview=False):
        with self.covered_sales():
            answer,trace=super().prepare(preview)
        coverage=getattr(self,'_order_coverage',None)
        if coverage:
            wb=sum('WB Statistics' in p['source'] for p in coverage['products'].values())
            answer+='\nДополнение заказов пропущенных карточек: MPStats — '+str(len(coverage['products'])-wb)+', WB — '+str(wb)+'. Прибыль и воронка ими не подменяются.'
            if coverage.get('remaining'):
                answer+='\nЗаказы ещё не проверены: '+', '.join(coverage['remaining'].values())+'.'
            trace.append(dict(name='china_order_catalogue_coverage',**self.audit['order_coverage']))
        if self.audit.get('mode')=='intraday':
            from china_agent.price_brief import render_plain as brief
            review=self.get('china_agent:daily_expected_candidates:'+str(self.day))
            from china_agent.buyer_price_forecast import load
            buyer=load(self)
            trace.append(dict(name='china_buyer_price_forecast',**buyer))
            omitted=[]
            answer=brief(answer,'intraday',review,self.day,self.get('china_agent:prices:v1'),buyer,omitted=omitted)
            if omitted:trace.append(dict(name='china_price_proposal_exclusions',products=omitted))
        return answer,trace

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--mode',choices=('morning','intraday'),required=True);parser.add_argument('--verify',action='store_true')
    args=parser.parse_args();w=CoverageWorker(args.mode)
    try:
        w.run(preview=args.verify)
        w.save('china_agent:coverage_report:'+str(w.day)+':'+args.mode+(':verify' if args.verify else ''),w.audit)
        print(json.dumps({k:w.audit.get(k) for k in ('status','order_coverage','wb_writes','telegram_message_ids')}))
    finally:
        import requests
        requests.sessions.Session.request=w.original_http

if __name__=='__main__':main()
