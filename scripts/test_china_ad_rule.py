import unittest,copy
from unittest.mock import patch
from datetime import datetime,timezone,timedelta
from types import SimpleNamespace
import china_ad_rule as rule
from china_loss_control import CHAT,BOT,OWNER,PLAN,digest
def campaign(ids):
 return dict(id=10,status=9,bid_type='manual',currency='CNY',settings=dict(payment_type='cpc',placements=dict(search=False,recommendations=True)),restrictions=dict(can_change_nms=True),nm_settings=[dict(nm_id=n,bids_kopecks=dict(search=0,recommendations=50)) for n in ids])
class IO:
 def __init__(self):self.mem={};self.writes=[];self.c={10:campaign([1,2,3])};self.fail=False;self.owner=True
 def get(self,k):return copy.deepcopy(self.mem.get(k))
 def put(self,k,p):self.mem[k]=copy.deepcopy(p)
 def create(self,k,p):
  if k in self.mem:return False
  self.put(k,p);return True
 def validate_owner(self,a):
  if not self.owner:raise PermissionError('owner')
 def read(self,io,ids=None):return copy.deepcopy(self.c if ids is None else {i:self.c[i] for i in ids})
 def http(self,io,path,method='GET',body=None):
  self.writes.append((path,copy.deepcopy(body)))
  if path=='/api/advert/v1/bids':
   for b in body['bids']:
    for n in b['nm_bids']:
     next(x for x in self.c[b['advert_id']]['nm_settings'] if x['nm_id']==n['nm_id'])['bids_kopecks'][n['placement']]=n['bid_kopecks']
  elif path=='/adv/v0/auction/nms':
   for b in body['nms']:self.c[b['advert_id']]['nm_settings']=[n for n in self.c[b['advert_id']]['nm_settings'] if n['nm_id'] not in b['nms']['delete']]
  else:raise AssertionError('unapproved endpoint')
  if self.fail:self.fail=False;raise TimeoutError('lost receipt')
  return {}
def plan():
 items=[dict(id='10:1',kind='ad_set_bid',article='one',campaign_id=10,nm_id=1,old_minor=50,target_minor=28),dict(id='10:2',kind='ad_exclude_sku',article='two',campaign_id=10,nm_id=2)]
 return dict(plan_id='test',plan_sha256=digest(items),items=items,expires_at=(datetime.now(timezone.utc)+timedelta(hours=1)).isoformat())
class Rules(unittest.TestCase):
 def test_boundaries_and_last_sku_protection(self):
  rows=[dict(nm='1',article='one',drr=6,orders=2),dict(nm='2',article='two',drr=10,orders=2),dict(nm='3',article='three',drr=10.1,orders=2)]
  items=rule.items_for(rows,{10:campaign([1,2,3])},{(10,1):28,(10,2):28})
  self.assertEqual([i['kind'] for i in items],['ad_set_bid','ad_set_bid','ad_exclude_sku'])
  blocked=rule.items_for([dict(nm='1',article='one',drr=12)],{10:campaign([1])},{})
  self.assertEqual(blocked[0]['kind'],'needs_data')
 def test_collective_empty_campaign_blocked(self):
  rows=[dict(nm=str(n),article=str(n),drr=12) for n in (1,2)]
  self.assertTrue(all(i['kind']=='needs_data' for i in rule.items_for(rows,{10:campaign([1,2])},{})))
 def test_campaign_specific_selection(self):
  a=campaign([1,2]);b=campaign([1,3])
  items=rule.items_for([dict(nm='1',campaign_id=10,article='one',drr=12)],{10:a,20:b},{})
  self.assertEqual([i['campaign_id'] for i in items],[10])
 def test_exact_writes_and_repeated_approval(self):
  io=IO();p=plan();a=dict(plan_sha256=p['plan_sha256'])
  with patch('china_loss_ads.current',io.read),patch('china_loss_ads.http',io.http),patch.object(rule,'minimums',return_value={1:28}):
   e=rule.execute(io,a,p);again=rule.execute(io,a,p)
  self.assertEqual(e,again);self.assertEqual(len(io.writes),2)
  self.assertEqual(e['status'],'done')
  self.assertEqual([n['nm_id'] for n in io.c[10]['nm_settings']],[1,3])
  self.assertEqual(io.c[10]['nm_settings'][1]['bids_kopecks']['recommendations'],50)
 def test_timeout_never_replays_write(self):
  io=IO();io.fail=True;p=plan();p['items']=p['items'][:1];p['plan_sha256']=digest(p['items']);a=dict(plan_sha256=p['plan_sha256'])
  with patch('china_loss_ads.current',io.read),patch('china_loss_ads.http',io.http),patch.object(rule,'minimums',return_value={1:28}):
   self.assertEqual(rule.execute(io,a,p)['items'][0]['status'],'uncertain')
   self.assertEqual(rule.execute(io,a,p)['items'][0]['status'],'verified')
  self.assertEqual(len(io.writes),1)
 def test_owner_required(self):
  io=IO();io.owner=False;p=plan()
  with self.assertRaises(PermissionError):rule.execute(io,dict(plan_sha256=p['plan_sha256']),p)
  self.assertEqual(io.writes,[])
 def test_owner_reply_binding(self):
  p=plan();p['chat_id']=CHAT;p['bot_id']=BOT
  mem={PLAN+p['plan_id']:p,'china_agent:ad_rule_message:123':dict(plan_id=p['plan_id'],plan_sha256=p['plan_sha256'])}
  w=SimpleNamespace(now=datetime.now(timezone.utc),get=lambda k:mem.get(k),save=lambda k,p,**kw:mem.update({k:p}))
  job=dict(id=9,sender_id=1,chat_id=CHAT,request_text='Сделай всё',tool_trace=[dict(name='china_saved_question',reply_message_id=123,bot_id=BOT,message_id=100)],update_id=1,created_at=w.now.isoformat())
  self.assertIn('действующие участники',rule.handle(w,job)[0])
  self.assertFalse(any(k.startswith(rule.APPROVAL) for k in mem))
  job['sender_id']=OWNER;self.assertIn('Принято',rule.handle(w,job)[0])
  self.assertTrue(any(k.startswith(rule.APPROVAL) for k in mem))
 def test_other_member_can_confirm_when_delegated(self):
  p=plan();p['chat_id']=CHAT;p['bot_id']=BOT
  mem={PLAN+p['plan_id']:p,'china_agent:ad_rule_message:123':dict(plan_id=p['plan_id'],plan_sha256=p['plan_sha256']),'china_agent:command_permissions:v2':dict(enabled=True,policy='all_current_human_group_members',chat_id=CHAT,bot_id=BOT)}
  w=SimpleNamespace(now=datetime.now(timezone.utc),get=lambda k:mem.get(k),save=lambda k,p,**kw:mem.update({k:p}),member_check=lambda actor:dict(status='member',user=dict(id=actor,is_bot=False)))
  job=dict(id=99,sender_id=42,chat_id=CHAT,request_text='Сделай всё',tool_trace=[dict(name='china_saved_question',reply_message_id=123,bot_id=BOT,message_id=100)],update_id=99,created_at=w.now.isoformat())
  self.assertIn('Принято',rule.handle(w,job)[0])
  self.assertEqual(mem[rule.APPROVAL+'99']['sender_id'],42)
 def test_trend_keep_recommendations_do_not_write(self):
  io=IO();p=plan();p['items']=[dict(id='keep',kind='keep_ad_settings',article='one',campaign_id=10,nm_id=1,old_minor=50),dict(id='outside',kind='keep_outside_ads',article='four',campaign_id=0,nm_id=4)];p['plan_sha256']=digest(p['items'])
  with patch('china_loss_ads.current',io.read):
   e=rule.execute(io,dict(plan_sha256=p['plan_sha256']),p)
  self.assertEqual([s['status'] for s in e['items']],['verified','verified']);self.assertEqual(io.writes,[])
 def test_trend_png_binds_exact_plan(self):
  import base64,hashlib
  p=plan();p.update(chat_id=CHAT,bot_id=BOT,report_message_ids=[])
  key='china_agent:ad_cost_png:question:9:v1'
  manifest=dict(status='frozen',chat_id=CHAT,job_id=9,plan_id=p['plan_id'],plan_sha256=p['plan_sha256'],files=[])
  mem={PLAN+p['plan_id']:p,key:manifest}
  w=SimpleNamespace(get=lambda k:mem.get(k),save=lambda k,p,**kw:mem.update({k:p}))
  rule.bind(w,'CHINA_AD_COST_PNG:'+key+':0',321)
  self.assertEqual(mem['china_agent:ad_rule_message:321']['plan_sha256'],p['plan_sha256'])
  self.assertEqual(mem[PLAN+p['plan_id']]['report_message_ids'],[321])
 def test_read_guard_no_mutations(self):
  with rule.reads() as scope:
   scope[10]={1,2}
   b=dict(advert_id=10,nm_ids=[1],payment_type='cpc',placement_types=['recommendation'])
   self.assertTrue(rule.allowed_read('POST','https://advert-api.wildberries.ru/api/advert/v1/bids/min',b))
   self.assertFalse(rule.allowed_read('PATCH','https://advert-api.wildberries.ru/api/advert/v1/bids',{}))
   self.assertFalse(rule.allowed_read('GET','https://advert-api.wildberries.ru/adv/v0/pause?id=10',{}))
   b['nm_ids']=[99];self.assertFalse(rule.allowed_read('POST','https://advert-api.wildberries.ru/api/advert/v1/bids/min',b))
if __name__=='__main__':unittest.main()
