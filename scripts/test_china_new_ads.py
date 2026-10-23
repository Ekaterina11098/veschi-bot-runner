import copy,unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import china_new_ads as n
from china_loss_control import CHAT,BOT,digest,is_all

def plan():
 items=[]
 for i,g in enumerate(['orders','demand']):items.append(dict(id=g,kind='ad_create_campaign',group=g,name='test-'+g,skus=[dict(nm_id=i+1,article='article-'+g,bid_minor=28 if i==0 else 23)],payment_type='cpc',bid_type='manual',placements=['recommendations'],budget_cny=100,daily_limit_minor=10000,carry_over_enabled=False,auto_topup=False))
 return dict(plan_id='new-test',chat_id=CHAT,bot_id=BOT,execution_kind='ad_create_campaigns',items=items,plan_sha256=digest(items),expires_at=(datetime.now(timezone.utc)+timedelta(hours=2)).isoformat(),created_at=datetime.now(timezone.utc).isoformat(),report_message_ids=[77],price_changes=False)

class IO:
 def __init__(self,p):self.mem={n.BIND+'77':dict(plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],chat_id=CHAT)};self.authorized=True
 def get(self,k):return copy.deepcopy(self.mem.get(k))
 def put(self,k,v):self.mem[k]=copy.deepcopy(v)
 def create(self,k,v):
  if k in self.mem:return False
  self.put(k,v);return True
 def validate_owner(self,a):
  if not self.authorized:raise PermissionError('member left')

class Transport:
 def __init__(self):self.c={};self.b={};self.l={};self.writes=[];self.fail=None;self.bad_second_min=False;self.mindaily=10000
 def config(self):return dict(currency='CNY',minTopUp=10000,minDailyLimit=self.mindaily,cpcStep=1)
 def preflight(self,items,owned):pass
 def campaign(self,cid):return copy.deepcopy(self.c[cid])
 def minima(self,cid,ids):return {i:1000 if self.bad_second_min and cid==102 else (28 if i==1 else 23) for i in ids}
 def budget(self,cid):return self.b[cid]
 def limit(self,cid):return copy.deepcopy(self.l[cid])
 def request(self,path,method='GET',body=None):
  self.writes.append((path,method,copy.deepcopy(body)))
  if path=='/adv/v2/seacat/save-ad':
   cid=101+len(self.c);self.c[cid]=dict(id=cid,status=4,currency='CNY',bid_type='manual',settings=dict(name=body['name'],payment_type='cpc',placements=dict(search=False,recommendations=True)),nm_settings=[dict(nm_id=i,bids_kopecks=dict(search=0,recommendations=1)) for i in body['nms']]);self.b[cid]=0;result=cid
  elif path=='/api/advert/v1/bids':
   for campaign in body['bids']:
    for b in campaign['nm_bids']:next(nm for nm in self.c[campaign['advert_id']]['nm_settings'] if nm['nm_id']==b['nm_id'])['bids_kopecks']['recommendations']=b['bid_kopecks']
   result={}
  elif path=='/api/advert/v0/daily-limits':
   for cid in body['advertIds']:self.l[cid]=dict(advertId=cid,currency='CNY',enabled=True,dailyLimit=body['dailyLimit'],carryOverEnabled=body['carryOverEnabled'],valid=True)
   result={}
  elif path.startswith('/adv/v1/budget/deposit'):
   cid=int(path.split('id=')[1]);self.b[cid]+=body['sum'];result={}
  elif path.startswith('/adv/v0/start'):
   cid=int(path.split('id=')[1]);self.c[cid]['status']=9;result={}
  else:raise AssertionError(path)
  if self.fail and self.fail in path:raise TimeoutError('response lost after side effect')
  return result

class NewAds(unittest.TestCase):
 def setup(self):
  p=plan();io=IO(p);a=dict(plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],reply_message_id=77);return p,io,a,Transport()
 def test_two_drafts_limits_budgets_before_first_launch(self):
  p,io,a,t=self.setup();e=n.execute(io,a,p,t)
  self.assertEqual(e['status'],'done');self.assertEqual([t.b[i] for i in [101,102]],[100,100]);self.assertEqual(len(t.writes),10)
  first=next(i for i,r in enumerate(t.writes) if '/start' in r[0]);self.assertEqual(sum('/deposit' in r[0] for r in t.writes[:first]),2)
  self.assertEqual([t.l[i]['dailyLimit'] for i in [101,102]],[10000,10000]);self.assertTrue(all(not t.l[i]['carryOverEnabled'] for i in [101,102]))
  count=len(t.writes);n.execute(io,a,p,t);n.execute(io,dict(a,job_id=999),p,t);self.assertEqual(len(t.writes),count)
 def test_timeout_after_deposit_never_deposits_or_creates_again(self):
  p,io,a,t=self.setup();t.fail='budget/deposit';e=n.execute(io,a,p,t);self.assertEqual(e['status'],'uncertain');self.assertEqual(t.b[101],100)
  count=len(t.writes);n.execute(io,a,p,t);self.assertEqual(len(t.writes),count);self.assertEqual(sum('/start' in r[0] for r in t.writes),0)
 def test_timeout_after_create_never_creates_duplicate(self):
  p,io,a,t=self.setup();t.fail='save-ad';self.assertEqual(n.execute(io,a,p,t)['status'],'uncertain');n.execute(io,a,p,t);self.assertEqual(len(t.c),1)
 def test_second_minimum_failure_leaves_both_unlaunched_unfunded(self):
  p,io,a,t=self.setup();t.bad_second_min=True;e=n.execute(io,a,p,t);self.assertEqual(e['status'],'blocked');self.assertEqual(sum(t.b.values()),0);self.assertTrue(all(c['status']==4 for c in t.c.values()))
 def test_changed_config_does_not_create_any_campaign(self):
  p,io,a,t=self.setup();t.mindaily=20000;self.assertEqual(n.execute(io,a,p,t)['status'],'blocked');self.assertEqual(t.writes,[])
 def test_mutated_amount_and_wrong_reply_refused_before_writes(self):
  p,io,a,t=self.setup();p['items'][0]['budget_cny']=200
  with self.assertRaises(ValueError):n.execute(io,a,p,t)
  self.assertEqual(t.writes,[])
  p,io,a,t=self.setup();a['reply_message_id']=78
  with self.assertRaises(ValueError):n.execute(io,a,p,t)
  self.assertEqual(t.writes,[])
 def test_departed_member_cannot_execute(self):
  p,io,a,t=self.setup();io.authorized=False
  with self.assertRaises(PermissionError):n.execute(io,a,p,t)
  self.assertEqual(t.writes,[])
 def test_plain_positive_vs_negation_and_questions(self):
  for s in ['делай','согласен','согласна','да, делай','подтверждаю','запускай','сделай всё','можно запускать','одобряю','давай']:
   self.assertTrue(is_all(s),s)
  for s in ['не делай','не согласен','согласен?','можно запускать?','да, но бюджет 500','если всё хорошо, запускай','делай завтра','это пример: делай']:
   self.assertFalse(is_all(s),s)
 def test_reply_to_bound_png_only_queues_exact_scope(self):
  p,io,a,t=self.setup();io.put(n.PLAN+p['plan_id'],p)
  class W:
   now=datetime.now(timezone.utc)
   get=io.get
   def save(self,k,v,insert=False):return io.create(k,v) if insert else io.put(k,v)
  job=dict(id=10,update_id=90,sender_id=22,chat_id=CHAT,created_at=W.now.isoformat(),request_text='согласен',tool_trace=[dict(name='china_saved_question',bot_id=BOT,message_id=88,reply_message_id=77)])
  with patch('china_group_permissions.allowed',return_value=True):answer,trace=n.handle(W(),job)
  self.assertEqual(io.get(n.APPROVAL+'10')['plan_sha256'],p['plan_sha256']);self.assertEqual(trace[0]['name'],'new_ad_campaigns_approval');self.assertEqual(t.writes,[])
  with patch('china_group_permissions.allowed',return_value=True):answer,trace=n.handle(W(),dict(job,id=11))
  self.assertIsNone(io.get(n.APPROVAL+'11'));self.assertEqual(trace[0]['name'],'new_ad_already_approved')
 def test_report_request_collects_only_after_dialog_and_cannot_approve(self):
  p,io,a,t=self.setup()
  class W:
   now=datetime.now(timezone.utc)
   get=io.get
   def save(self,k,v,insert=False):return io.create(k,v) if insert else io.put(k,v)
  job=dict(id=12,sender_id=22,chat_id=CHAT,created_at=W.now.isoformat(),request_text='Подбери рекламный тест по всем кандидатам',tool_trace=[dict(name='china_saved_question',bot_id=BOT,message_id=91)])
  with patch('china_group_permissions.allowed',return_value=True):answer,trace=n.handle(W(),job)
  self.assertEqual(io.get(n.REQUEST+'12')['status'],'pending');self.assertIsNone(io.get(n.APPROVAL+'12'));self.assertEqual(t.writes,[])
 def test_candidate_selection_respects_ms_stock_costs_and_ad_history(self):
  from china_new_ad_reports import choose
  product=dict(nm_id=1,sa_name='bag',finished_orders=6,is_payed=4,open_card_count=100,funnel_orders_count=10,price_after_spp=1000,price_after_discount=1200,advertisement=0,subject_id=50)
  s=dict(memory_used=True,experience=dict(experiences=[],recent_changed_nm_ids=[]),campaigns={},protected=[],prices=[dict(nmID=1,sizes=[dict(discountedPrice=200)])],stock=[dict(article='bag',stock=50,reserve=2,price=10000)],orders=[dict(nmId=1)],products=[product],policy=dict(logistics_by_nm={'1':dict(delivery_cny=10)},category_minimum_minor={'50':28}))
  without_memory=dict(s,memory_used=False)
  with self.assertRaises(ValueError):choose(without_memory)
  g,missing=choose(s);self.assertEqual(g['orders'][0]['stock'],48)
  s['stock'][0]['reserve']=50;self.assertEqual(choose(s)[0]['orders'],[])
  s['stock'][0]['reserve']=0;s['products'][0]['advertisement']=100;self.assertEqual(choose(s)[0]['orders'],[])
  s['products'][0]['advertisement']=0;s['protected']=[1];self.assertEqual(choose(s)[0]['orders'],[])

if __name__=='__main__':unittest.main()

