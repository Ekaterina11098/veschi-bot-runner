import ast,copy,sys,types,unittest
from datetime import datetime,date,timedelta,timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from china_price_selection import choose

class Selection(unittest.TestCase):
    def select(self,change=None,before=.1,after=.1,nm='123',counts=None,profit=None):
        day=date(2026,11,9);entry=dict(article='123-Test-black',price=dict(current_cny=100))
        if change:entry.update(increase=change,last_price_change=change)
        state={'price_history':{nm:entry}}
        catalogue=dict(cabinet='token_3',rows=[dict(nmID=int(nm),vendorCode='123-Test-black')])
        audit={};saved={}
        w=types.SimpleNamespace(day=day,now=datetime(2026,11,9,tzinfo=timezone(timedelta(hours=3))),audit=audit,
            completed_products=lambda:([dict(nm_id=nm,sparkline_orders=counts or [1,1,1,1],orders_count=sum(counts or [1,1,1,1]))],{'id':1}),
            get=lambda k:state,save=lambda k,v:saved.update({k:v}),db=lambda *a,**kw:[])
        demand=types.SimpleNamespace(STATE_KEY='state',live_prices=lambda *a:catalogue,offer=lambda row:dict(current_cny=100,target_cny=105,base_cny=200,discount=50,target_base_cny=210))
        def period(worker,a,b):
            cr=after if a=='2026-11-05' else before
            return [dict(nm_id=nm,open_card_count=100,funnel_orders_count=cr*100)],{'id':2}
        modules={
            'china_agent':types.SimpleNamespace(demand=demand),
            'china_agent.control_owner_preview':types.SimpleNamespace(Preview=types.SimpleNamespace(acquire=lambda *a:None)),
            'china_agent.daily_report_worker':types.SimpleNamespace(MSK=timezone(timedelta(hours=3))),
            'china_agent.price_economic_target':types.SimpleNamespace(verified_price_history=lambda w:{}),
            'china_price_period':types.SimpleNamespace(period=period),
            'china_price_evidence':types.SimpleNamespace(valid_daily_orders=lambda r,n:len(r['sparkline_orders'])==n),
            'china_agent.price_brief':types.SimpleNamespace(render_plain=lambda text,*a,**kw:text),
            'china_agent.buyer_price_forecast':types.SimpleNamespace(load=lambda w:{}),
            'china_agent.daily_expected_control':types.SimpleNamespace(build=lambda *a,**kw:dict(status='complete',products=[])),
            'business_agents':types.ModuleType('business_agents'),
            'business_agents.data':types.SimpleNamespace(Data=lambda *a:types.SimpleNamespace(excluded=lambda a:False))}
        with patch.dict(sys.modules,modules):answer,trace=choose(w,True)
        self.assertFalse(saved)
        return answer,audit
    def change(self,day):return dict(detected_at=day+'T12:00:00+03:00',before_price=dict(current_cny=95),after_price=dict(current_cny=100))
    def test_repeat_conversion_maintained_does_not_require_profit_growth(self):
        answer,a=self.select(self.change('2026-11-04'),profit=-100)
        self.assertEqual(a['assessment']['candidate_count'],1)
    def test_changed_day_and_three_full_days_do_not_qualify(self):
        _,a=self.select(self.change('2026-11-05'))
        self.assertEqual(a['assessment']['candidate_count'],0)
    def test_declining_conversion_and_holds_do_not_raise(self):
        for kwargs in ({'before':.2,'after':.1},{'nm':'1473245494'}):
            with self.subTest(kwargs=kwargs):
                _,a=self.select(self.change('2026-11-04'),**kwargs)
                self.assertEqual(a['assessment']['candidate_count'],0)

class Coverage(unittest.TestCase):
    def test_present_aggregate_gets_verified_daily_orders_without_erasing_finance(self):
        module=ast.parse((Path(__file__).parent/'china_coverage_worker.py').read_text(encoding='utf8'))
        node=next(n for n in module.body if isinstance(n,ast.FunctionDef) and n.name=='overlay')
        env=dict(copy=copy,date=date,timedelta=timedelta);exec(compile(ast.Module(body=[node],type_ignores=[]),'overlay','exec'),env)
        report=dict(cabinet='token_3',date_from='2026-11-05',date_to='2026-11-08',available=False,products={'123':dict(orders=10,order_days=None,sales=2,profit=987)})
        coverage=dict(cabinet='token_3',period_from=report['date_from'],period_to=report['date_to'],status='complete',catalogue_count=1,products={'123':dict(status='complete',period_from=report['date_from'],period_to=report['date_to'],orders_each_day=[1,2,3,4],orders=10,article='123-Test-black',source='WB daily')})
        result=env['overlay'](report,coverage)
        self.assertEqual(len(result['products']['123']['order_days']),10)
        self.assertEqual(result['products']['123']['profit'],987)
        self.assertTrue(result['available'])
if __name__=='__main__':unittest.main()

