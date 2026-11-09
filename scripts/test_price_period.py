import sys,types,unittest
from datetime import timezone,timedelta
from unittest.mock import patch
from china_price_period import period

class Period(unittest.TestCase):
    def fixture(self):
        return dict(id=1,collected_at='2026-11-09T04:00:00Z',payload=[dict(tool='lk_wb_products',scope_verified=True,status='received',arguments=dict(date_from='2026-11-05',date_to='2026-11-08',start_row=0,end_row=1500),data={'data':dict(need_update=0,total=2,data=[dict(p_id=1,nm_id=10,sparkline_open_card=[1,2,3,4]),dict(p_id=2,nm_id=20,sparkline_open_card=None)])})])
    def get(self,row):
        modules={'analytics':types.ModuleType('analytics'),'analytics.mpstats_primary':types.SimpleNamespace(products=lambda *a:([],None)),
                 'china_agent':types.ModuleType('china_agent'),'china_agent.daily_report_worker':types.SimpleNamespace(MSK=timezone(timedelta(hours=3)))}
        w=types.SimpleNamespace(db=lambda *a,**kw:[row])
        with patch.dict(sys.modules,modules):return period(w,'2026-11-05','2026-11-08')
    def test_partial_sparkline_does_not_erase_scoped_raw_peers(self):
        rows,marker=self.get(self.fixture())
        self.assertEqual(len(rows),2)
        self.assertTrue(marker['per_product_period_validation_required'])
    def test_mismatched_period_pagination_and_unclosed_slice_rejected(self):
        for field in ['period','total','time']:
            row=self.fixture()
            if field=='period':row['payload'][0]['arguments']['date_to']='2026-11-07'
            if field=='total':row['payload'][0]['data']['data']['total']=3
            if field=='time':row['collected_at']='2026-11-08T04:00:00Z'
            with self.subTest(field=field):self.assertEqual(self.get(row),([],None))
if __name__=='__main__':unittest.main()

