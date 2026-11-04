"""No network credentials: exact addition writes are simulated and no replay is permitted."""
import copy,unittest
from datetime import datetime,timedelta,timezone
from unittest.mock import patch
from china_daily_ad_actions import execute
from china_loss_control import digest
class IO:
 def __init__(self):self.data={}
 def get(self,k):return copy.deepcopy(self.data.get(k))
 def put(self,k,v):self.data[k]=copy.deepcopy(v)
 def create(self,k,v):
  if k in self.data:return False
  self.put(k,v);return True
 def validate_owner(self,a):pass
class Response:
 ok=True;content=b'{}'
 def __init__(self,value):self.value=value
 def json(self):return copy.deepcopy(self.value)
class AdditionExecutionTests(unittest.TestCase):
 def run_add(self,fail_bid=False):
  io=IO();current=dict(id=7,status=9,currency='CNY',bid_type='manual',settings=dict(payment_type='cpc',placements=dict(recommendations=True,search=False)),restrictions=dict(can_change_nms=True),nm_settings=[dict(nm_id=1,subject=dict(id=50),bids_kopecks=dict(search=0,recommendations=28))])
  writes=[]
  def request(method,url,headers=None,json=None,timeout=None):
   if method=='GET':return Response(dict(adverts=[current]))
   writes.append((method,url,copy.deepcopy(json)))
   if '/auction/nms'in url:current['nm_settings'].append(dict(nm_id=2,subject=dict(id=50),bids_kopecks=dict(search=0,recommendations=28)))
   elif '/bids'in url:
    if fail_bid:raise RuntimeError('Lost response')
    current['nm_settings'][-1]['bids_kopecks']['recommendations']=30
   else:raise AssertionError('Unexpected mutation')
   return Response({})
  item=dict(id='7:add:2',kind='ad_add_sku',direction='add',campaign_id=7,nm_id=2,article='2-fixture',placement='recommendations',target_minor=30,subject_id=50)
  p=dict(plan_id='addition-fixture',execution_kind='daily_ad_actions_v2',items=[item],plan_sha256=digest([item]),expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
  a=dict(plan_sha256=p['plan_sha256'])
  io.token='fixture'
  with patch('requests.request',side_effect=request),patch('time.sleep'),patch('china_advertising_full_growth.validate_addition'),patch('china_execution_notice.deliver_result'):
   e=execute(io,a,p);again=execute(io,a,p)
  return e,again,writes,current
 def test_exact_add_then_bid_and_no_replay(self):
  e,again,writes,current=self.run_add()
  self.assertEqual(e['status'],'done');self.assertEqual(e['items'][0]['status'],'verified')
  self.assertEqual(len(writes),2)
  self.assertEqual(current['nm_settings'][0]['bids_kopecks']['recommendations'],28)
  self.assertEqual(current['nm_settings'][1]['bids_kopecks']['recommendations'],30)
 def test_uncertain_bid_never_repeats_membership_or_bid(self):
  e,again,writes,current=self.run_add(True)
  self.assertEqual(len(writes),2);self.assertEqual(again['items'][0]['status'],'uncertain')
  self.assertNotEqual(again['items'][0]['status'],'verified')
if __name__=='__main__':unittest.main()
