import copy,sys,types,unittest
from unittest.mock import patch
from china_advertising_reserve import checks,require,filter_bundle,refresh_before_send

class IO:
    def __init__(self):self.state={}
    def get(self,k):return copy.deepcopy(self.state.get(k))
    def create(self,k,v):
        if k in self.state:return False
        self.state[k]=copy.deepcopy(v);return True
    def put(self,k,v):self.state[k]=copy.deepcopy(v)

def addition():return dict(id='41298169:add:1473242577',kind='ad_add_sku',campaign_id=41298169,nm_id=1473242577,growth_evidence=dict(campaign_reserve_required_cny=1392.34))
def response(total):return dict(adverts=[dict(advertId=41298169,currency='CNY',total=total)])

class Reserve(unittest.TestCase):
    def api(self,body):
        return patch.dict(sys.modules,{'china_advertising_v2':types.SimpleNamespace(http=lambda *a,**kw:body)})
    def test_current_shortfall_is_saved_but_does_not_block_execution(self):
        io=IO()
        with self.api(response(1355)):
            self.assertEqual(require(io,addition())['status'],'ready_with_shortfall')
        record=next(iter(io.state.values()))
        self.assertEqual(record['items'][0]['status'],'reserve_shortfall')
        self.assertEqual(record['items'][0]['shortfall_cny'],37.34)
        self.assertEqual(record['budget_response'],response(1355))
    def test_prepare_keeps_addition_despite_reserve_shortfall(self):
        a=addition();other=dict(id='raise1',kind='ad_set_bid')
        bundle=dict(campaigns=[dict(focus=[dict(action=a),dict(action=other)],attention=[dict(action=a),dict(action=other)])])
        with self.api(response(1355)):out,ev=filter_bundle(IO(),bundle,'prepare')
        self.assertEqual(out['campaigns'][0]['focus'][0]['action'],a)
        self.assertEqual(out['campaigns'][0]['attention'],[dict(action=a),dict(action=other)])
        self.assertEqual(bundle['campaigns'][0]['focus'][0]['action'],a)
    def test_missing_and_wrong_currency_are_not_reported_as_shortage(self):
        for body,expected in [(dict(adverts=[]),'budget_unavailable'),(dict(adverts=[dict(advertId=41298169,currency='RUB',total=2000)]),'currency_mismatch')]:
            with self.api(body):r=checks(IO(),[addition()],'send')
            self.assertEqual(r['items'][0]['status'],expected)
    def test_batch_has_exact_campaign_scope_and_max_reserve(self):
        seen=[]
        def http(io,path,method,body):seen.append(body);return response(1400)
        a=addition();b=dict(a,id='second')
        with patch.dict(sys.modules,{'china_advertising_v2':types.SimpleNamespace(http=http)}):r=checks(IO(),[a,b],'prepare')
        self.assertEqual(seen,[dict(advertIds=[41298169])]);self.assertEqual(r['status'],'ready')
    def test_partial_delivery_never_rebuilds_or_reads_wb(self):
        io=IO();io.state['china_agent:advertising_delivery:2026-11-13:v1']=dict(parts=[dict(status='sent',message_id=1)])
        saved=dict(bundle={})
        with patch.dict(sys.modules,{'china_advertising_v2':types.SimpleNamespace(http=lambda *a: self.fail('Unexpected WB read'))}):
            self.assertIs(refresh_before_send(io,'2026-11-13',saved,'artifact'),saved)
    def test_send_rebuilds_unsigned_plan_only_when_budget_data_missing(self):
        io=IO();a=addition();saved=dict(day='2026-11-13',status='frozen',bundle=dict(campaigns=[dict(focus=[dict(action=a)],attention=[dict(action=a)])]),files=[dict(plan_id='old')])
        io.state['china_agent:loss_plan:v1:old']=dict(report_message_ids=[])
        pages=[dict(kind='drr',family='drr',page=1,total=1,bytes=b'png',actions=[])]
        def plan(io,day,f,index,slot):
            self.assertTrue(slot.startswith('reserve-'));self.assertEqual(f['actions'],[])
            return dict(plan_id='new',plan_sha256='newhash',items=[])
        mods={'china_advertising_v2':types.SimpleNamespace(http=lambda *a,**kw:dict(adverts=[])),
              'china_advertising_v2_png':types.SimpleNamespace(render=lambda b:pages),
              'china_daily_ad_actions':types.SimpleNamespace(plan=plan)}
        with patch.dict(sys.modules,mods):out=refresh_before_send(io,'2026-11-13',saved,'artifact')
        self.assertEqual(out['files'][0]['action_count'],0)
        self.assertIn('invalidated_at',io.state['china_agent:loss_plan:v1:old'])
        self.assertEqual(io.state['artifact'],out)
        self.assertEqual(saved['files'][0]['plan_id'],'old')
    def test_send_does_not_remove_offer_for_shortfall(self):
        io=IO();a=addition();saved=dict(bundle=dict(campaigns=[dict(focus=[dict(action=a)],attention=[dict(action=a)])]))
        with self.api(response(0)):self.assertIs(refresh_before_send(io,'2026-11-13',saved,'artifact'),saved)
    def test_currency_precision_does_not_create_false_shortfall(self):
        a=addition();a['growth_evidence']['campaign_reserve_required_cny']=1392.3400000000001
        with self.api(response(1392.34)):self.assertEqual(require(IO(),a)['status'],'ready')
if __name__=='__main__':unittest.main()
