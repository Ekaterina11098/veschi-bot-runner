"""Owner-approved two-part China morning delivery, no WB mutations."""
import argparse, copy, json
from datetime import date, datetime, timedelta
from china_agent.scheduled_price_worker import ScheduledWorker
from china_agent.daily_report_worker import MSK
from china_agent import demand
from china_agent.price_sources import profit, period_conversion, days
from business_agents.sales import sales_report
from business_agents.data import Data

def tracked_rows(state, day):
    low=day-timedelta(days=4)
    rows=[]
    for nm, entry in state.get('price_history', {}).items():
        change=entry.get('last_price_change') or entry.get('increase') or {}
        try:
            detected=datetime.fromisoformat(change['detected_at']).astimezone(MSK).date()
        except (KeyError, ValueError, TypeError):
            continue
        # Retain pending cohorts until the first four-day assessment, even
        # after their detection date leaves the rolling four-day window.
        first_check=detected+timedelta(days=5)
        if low <= detected < day or (detected < day <= first_check):
            rows.append((nm,entry,change,detected))
    return sorted(rows,key=lambda r:r[1].get('article',r[0]))

def render_control(state, day, read, now):
    rows=tracked_rows(state,day)
    fmt=lambda v:'н/д' if v is None else f'{v:g}'.replace('.',',')
    pct=lambda v:'н/д' if v is None else f'{v:.1%}'.replace('.',',')
    lines=['Китай • контроль результата изменений цен • '+day.strftime('%d.%m.%Y'),
           'Окно изменений: '+(day-timedelta(days=4)).strftime('%d.%m')+'–'+(day-timedelta(days=1)).strftime('%d.%m')+'.',
           'Включены также незавершённые наблюдения до первой итоговой оценки.',
           'Под наблюдением: '+str(len(rows))+' товаров. Цена продавца после скидки, ¥: было → стало.']
    data=Data('china',read)
    for nm,e,c,detected in rows:
        before=(c.get('before_price') or {}).get('current_cny')
        after=(c.get('after_price') or {}).get('current_cny')
        n=max(0,(day-detected).days-1)
        check=detected+timedelta(days=5)
        lines.append('• '+e.get('article',nm)+': '+fmt(before)+' → '+fmt(after)+' ¥; замечено '+detected.strftime('%d.%m')+'.')
        if not n:
            # Shared zero-day cohort status is rendered once below.
            continue
        n=min(n,4)
        end=day-timedelta(days=1); start=end-timedelta(days=n-1)
        b_end=detected-timedelta(days=1); b_start=b_end-timedelta(days=n-1)
        pb=profit(read,nm,b_start,b_end); pa=profit(read,nm,start,end)
        cb=period_conversion(read,nm,b_start,b_end,now); ca=period_conversion(read,nm,start,end,now)
        report=sales_report(data,'token_3',start.isoformat(),end.isoformat(),now)
        p=report.get('products',{}).get(nm)
        counts=[p.get('order_days',[]).count(d) for d in days(start,end)] if report.get('available') and p else None
        lines.append('  '+b_start.strftime('%d.%m')+'–'+b_end.strftime('%d.%m')+' → '+start.strftime('%d.%m')+'–'+end.strftime('%d.%m')+
                     ': прибыль '+fmt(pb)+' → '+fmt(pa)+' ₽; конверсия '+pct(cb)+' → '+pct(ca)+
                     '; заказы после: '+('/'.join(map(str,counts)) if counts is not None else 'н/д')+'.')
        if n<4:
            verdict='Промежуточно; итоговая оценка '+check.strftime('%d.%m')+'.'
        elif any(v is None for v in (pb,pa,cb,ca,counts)):
            verdict='Недостаточно данных для полного решения.'
        elif pa<pb or ca<cb or not all(v>=1 for v in counts):
            verdict='Есть ухудшение: разобрать возврат к прежней цене с учётом связки; автоматического возврата нет.'
        elif pa>pb:
            verdict='Прибыль выросла; положительная динамика после повышения, причинность не доказана.'
        else:
            verdict='Рост прибыли не подтверждён; продолжаем наблюдение.'
        lines.append('  '+verdict)
    zero_dates=sorted({d for _,_,_,d in rows if day==d+timedelta(days=1)})
    for d in zero_dates:
        count=sum(x[3]==d for x in rows)
        lines.append(str(count)+' товаров с изменениями '+d.strftime('%d.%m')+': полных дней после изменения — 0. Прибыль и необходимость возврата пока не подтверждены. База '+(d-timedelta(days=4)).strftime('%d.%m')+'–'+(d-timedelta(days=1)).strftime('%d.%m')+'; наблюдение '+(d+timedelta(days=1)).strftime('%d.%m')+'–'+(d+timedelta(days=4)).strftime('%d.%m')+'; оценка '+(d+timedelta(days=5)).strftime('%d.%m')+'.')
    if not rows: lines.append('Новых зарегистрированных изменений и ожидающих первой оценки нет.')
    lines+=['День обнаружения и сегодняшний день исключены. Промежуточные периоды сравниваются при равной длительности.',
            'Дата обнаружения может отличаться от фактической даты изменения WB. Новая корректировка начинает отсчёт заново.',
            'Источник цен — сохранённые наблюдения WB; прибыль и конверсия — точные периоды MPStats. Нет данных ≠ ноль.',
            'Все изменения цены согласовываем.']
    return '\n'.join(lines)

class PairWorker(ScheduledWorker):
    def __init__(self,section):
        super().__init__('morning')
        self.section=section
        self.command='/china_morning_pair_'+section
        self.update_id=-(9800000000 if section=='candidates' else 9900000000)-(self.day-date(2020,1,1)).days
        self.audit.update(section=section)
    def prepare(self,preview=False):
        if self.section=='candidates':
            # The owner explicitly approved this already calculated October 16
            # report; subsequent days are generated from fresh completed days.
            if self.day==date(2026,10,16):
                rows=self.db('GET','business_agent_jobs',params=dict(id='eq.36',agent_id='eq.china',status='eq.done',limit=1)) or []
                if len(rows)!=1: raise RuntimeError('Approved October 16 report missing')
                answer=rows[0]['answer']
                if '2026-10-16' not in answer or '12.10–15.10' not in answer: raise RuntimeError('Approved period mismatch')
                trace=copy.deepcopy(rows[0].get('tool_trace') or [])
                trace=[e for e in trace if e.get('name')!='china_report_delivery']
                return answer,trace
            answer,trace=super().prepare(preview)
            expected=(self.day-timedelta(days=1)).isoformat()
            latest=self.audit.get('assessment') or {}
            if latest.get('period_to')!=expected: raise RuntimeError('Completed period mismatch')
            return answer,trace
        state=self.get(demand.STATE_KEY) or {}
        answer=render_control(state,self.day,lambda table,params:self.db('GET',table,params=params),self.now)
        return answer,[dict(name='china_price_daily_report',report_date=str(self.day),mode='control')]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--verify',action='store_true')
    args=parser.parse_args()
    for section in ('candidates','control'):
        w=PairWorker(section)
        try:
            w.run(preview=args.verify)
            w.save('china_agent:morning_pair:'+str(w.day)+':'+section+(':verify' if args.verify else ''),w.audit)
            print(json.dumps(dict(section=section,status=w.audit.get('status'),sent_parts=w.audit.get('sent_parts'),message_ids=w.audit.get('telegram_message_ids'),wb_writes=w.audit.get('wb_writes'))))
            if not args.verify and w.audit.get('status') not in ('delivered','already_delivered'):
                raise RuntimeError('First delivery not complete; stop before second')
        finally:
            # Restore transport before constructing the second isolated worker.
            import requests
            requests.sessions.Session.request=w.original_http
if __name__=='__main__':main()
