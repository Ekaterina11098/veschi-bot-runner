"""Offline proposals -> Telegram binding -> member consent -> exact execution."""
import copy,sys,types,unittest
from datetime import datetime,timezone,timedelta
from unittest.mock import patch
import china_bid_proposals as q
import china_advertising_plans as p
from china_loss_control import CHAT,BOT,digest
from china_group_permissions import KEY
class Work:
 now=datetime(2026,10,27,6,tzinfo=timezone.utc)
 def __init__(self):self.mem={};self.calls=[]
 def get(self,key):return copy.deepcopy(self.mem.get(key))
 def save(self,key,value,insert=False):
  if insert and key in self.mem:return False
  self.mem[key]=copy.deepcopy(value);return True
 def config(self):return dict(chat_id=CHAT,bot_id=BOT,owner_user_id=5122667182)
 def member_check(self,actor):return dict(status='member',user=dict(id=actor,is_bot=False))
def fixture():
 w=Work();w.mem[q.POLICY]=dict(enabled=True);w.mem[KEY]=dict(enabled=True,policy='all_current_human_group_members',chat_id=CHAT,bot_id=BOT)
 c=dict(id=10,status=9,currency='CNY',bid_type='manual',settings=dict(payment_type='cpc',placements=dict(search=False,recommendations=True)),timestamps=dict(started='2026-10-10T08:00:00+03:00'),nm_settings=[dict(nm_id=100,subject=dict(id=50),bids_kopecks=dict(search=0,recommendations=28))])
 stat=dict(advertId=10,currency='CNY',days=[dict(date='2026-10-'+d,apps=[dict(nms=[dict(nmId=100,sum=3,sum_price=300,orders=3,clicks=30)])]) for d in ['24','25','26','27']])
 w.mem['china_agent:advertising_source:2026-10-27:v2']=dict(observed_at='2026-10-27T04:00:00+00:00',status='complete',batches={'0':dict(campaigns=dict(adverts=[c]),stats=[stat])},executions=[],experience=[],config=dict(currency='CNY',cpcStep=1,cpcMaxBid=1000))
 econ=dict(observed_at='2026-10-27T04:00:00+00:00',products=[dict(nm_id=100,sa_name='one-bag',subject_id=50,finished_orders=20,is_payed=10,total_commission_without_spp_in_sales=20,sales_sum_without_spp=1000,price_after_discount=100,price_after_spp=83)],stock=[dict(article='one-bag',stock=100,reserve=1,price=1000)],prices=[dict(nmID=100,currencyIsoCode4217='CNY',sizes=[dict(discountedPrice=100)])],policy=dict(logistics_by_nm={'100':dict(delivery_cny=10)}))
 w.mem['china_agent:new_ad_source:v1:2026-10-27']=econ
 j=dict(id=8,update_id=88,sender_id=42,chat_id=CHAT,created_at=w.now.isoformat(),request_text='Выбери 10 товаров и подними ставки на 30%',tool_trace=[dict(name='china_saved_question',bot_id=BOT,message_id=81)])
 def refresh(kind,ids,view):
  w.calls.append(kind);return dict(campaigns={10:copy.deepcopy(c)},stats={10:copy.deepcopy(stat)},config=dict(currency='CNY',cpcStep=1,cpcMaxBid=1000),minimums={'10:100':28},observed_at=w.now.isoformat())
 return w,j,c,stat,refresh
class ProposalTests(unittest.TestCase):
 def test_auto_select_percent_rounding_and_no_write(self):
  w,j,c,stat,refresh=fixture();r=q.prepare(w,j,refresh=refresh)
  self.assertEqual(r['status'],'ready');self.assertEqual(r['items'][0]['target_minor'],36);self.assertEqual(r['wb_writes'],0)
  self.assertIn('Подошло 1 из запрошенных 10',r['text'])
  self.assertEqual(w.calls,['campaigns'])
  again=q.prepare(w,j,refresh=refresh);self.assertEqual(again['plan_id'],r['plan_id']);self.assertEqual(w.calls,['campaigns'])
 def test_recent_bid_with_nm_field_in_registry_blocks_without_read(self):
  w,j,c,stat,refresh=fixture();after=copy.deepcopy(c);after['nm_settings'][0]['bids_kopecks']['recommendations']=36
  w.mem['china_agent:verified_campaign_state:v1']={'10':'receipt'}
  w.mem['receipt']=dict(status='verified',before=c,after=after,items=[dict(nm=100,old=28,target=36)],verified_at='2026-10-27T05:00:00+00:00')
  r=q.prepare(w,j,refresh=refresh);self.assertEqual(r['status'],'blocked');self.assertEqual(w.calls,[])
  self.assertIn('полного дня',r['note'])
 def test_change_day_excluded_one_next_full_day_accepted(self):
  w,j,c,stat,refresh=fixture();old=copy.deepcopy(c);old['nm_settings'][0]['bids_kopecks']['recommendations']=25
  s=w.mem['china_agent:advertising_source:2026-10-27:v2'];s['executions']=[dict(payload=dict(status='verified',before=old,after=c,verified_at='2026-10-25T12:00:00+00:00'))]
  r=q.prepare(w,j,refresh=refresh);self.assertEqual(r['items'][0]['evidence']['decision_days'],['2026-10-26'])
 def test_today_high_drr_dropped_after_fresh_read(self):
  w,j,c,stat,refresh=fixture()
  def fresh(*args):
   r=refresh(*args);r['stats'][10]['days'][-1]['apps'][0]['nms'][0].update(sum=30);return r
  r=q.prepare(w,j,refresh=fresh);self.assertEqual(r['status'],'blocked')
  self.assertFalse(any(k.startswith(p.P) for k in w.mem))
 def test_negative_economics_never_proposes_or_reads(self):
  w,j,c,stat,refresh=fixture();w.mem['china_agent:new_ad_source:v1:2026-10-27']['products'][0]['is_payed']=0
  r=q.prepare(w,j,refresh=refresh);self.assertEqual(r['status'],'blocked');self.assertEqual(w.calls,[])
 def test_unknown_economics_not_replaced_by_zero(self):
  w,j,c,stat,refresh=fixture();w.mem['china_agent:new_ad_source:v1:2026-10-27']['stock']=[]
  self.assertEqual(q.prepare(w,j,refresh=refresh)['status'],'blocked');self.assertEqual(w.calls,[])
 def test_any_current_member_can_confirm_bid_plan(self):
  w,j,c,stat,refresh=fixture();r=q.prepare(w,j,refresh=refresh);p.bind(w,r['text'],71)
  # Confirm by another real member, not just the proposer/Pavel/owner.
  j.update(id=9,sender_id=77,created_at=datetime.now(timezone.utc).isoformat(),request_text='поднимай',tool_trace=[dict(name='china_saved_question',bot_id=BOT,message_id=82,reply_message_id=71)])
  w.now=datetime.now(timezone.utc)
  answer,trace=p.handle(w,j);self.assertIn('Принято',answer)
  a=w.get(p.A+r['plan_id']);self.assertEqual(a['sender_id'],77);self.assertEqual(a['execution_kind'],'advertising_dialog_v1')
  self.assertIn('уже принят',p.handle(w,j)[0])
 def test_left_member_and_negation_do_not_confirm(self):
  w,j,c,stat,refresh=fixture();r=q.prepare(w,j,refresh=refresh);p.bind(w,r['text'],71)
  j['tool_trace'][0]['reply_message_id']=71
  for cmd in ['не поднимай','поднимай на 50%','поднимай и удали РК']:
   j['request_text']=cmd;self.assertIsNone(p.handle(w,j))
  j['request_text']='поднимай';w.member_check=lambda actor:dict(status='left',user=dict(id=actor,is_bot=False))
  self.assertIn('участникам',p.handle(w,j)[0])
 def test_revoked_plan_and_pre_publication_command_rejected(self):
  w,j,c,stat,refresh=fixture();r=q.prepare(w,j,refresh=refresh);p.bind(w,r['text'],71);j['tool_trace'][0]['reply_message_id']=71;j['request_text']='поднимай'
  self.assertIn('до публикации',p.handle(w,j)[0])
  w.mem[p.P+r['plan_id']]['invalidated_at']='2026-10-27T06:01:00+00:00'
  self.assertIn('отозван',p.handle(w,j)[0])
 def test_raise_alias_cannot_approve_add_plan(self):
  w,j,c,stat,refresh=fixture();r=q.prepare(w,j,refresh=refresh);pid=r['plan_id'];v=w.mem[p.P+pid];v['items'][0]['kind']='ad_add_sku';v['plan_sha256']=digest(v['items']);p.bind(w,v['text'],71)
  j['request_text']='поднимай';j['tool_trace'][0]['reply_message_id']=71
  self.assertIn('только к плану ставок',p.handle(w,j)[0])
 def test_explicit_percentage_not_drr_multiplier(self):
  w,j,c,stat,refresh=fixture();j['request_text']='Предложи ставки';r=q.prepare(w,j,raise_percent=20,count=1,refresh=refresh)
  self.assertEqual(r['items'][0]['target_minor'],34)
  self.assertNotEqual(r['items'][0]['target_minor'],round(28*5))
 def test_future_price_change_blocks_before_network(self):
  w,j,c,stat,refresh=fixture();before=dict(nmID=100,currencyIsoCode4217='CNY',sizes=[dict(discountedPrice=90)]);after=dict(nmID=100,currencyIsoCode4217='CNY',sizes=[dict(discountedPrice=100)])
  w.mem['china_agent:advertising_source:2026-10-27:v2']['executions']=[dict(payload=dict(status='verified',before=before,after=after,verified_at='2026-10-26T20:00:00+00:00'))]
  r=q.prepare(w,j,refresh=refresh);self.assertEqual(r['status'],'blocked');self.assertEqual(w.calls,[])
if __name__=='__main__':unittest.main()

class ExecutionPermissionTests(unittest.TestCase):
 def make_io(self,command='поднимай',kind='advertising_dialog_v1'):
  import base64,json
  try:import requests
  except ModuleNotFoundError:sys.modules.setdefault('requests',types.ModuleType('requests'))
  from china_loss_execute import IO
  class TestIO(IO):
   def __init__(self):
    claims=dict(t=False,exp=4102444800,s=8,sid='seller')
    self.token='x.'+base64.urlsafe_b64encode(json.dumps(claims).encode()).decode().rstrip('=')+'.x'
   def db(self,path,*args,**kwargs):
    if path.startswith('business_agent_config'):return [dict(active=True,chat_id=CHAT,bot_id=BOT,owner_user_id=5122667182)]
    if path.startswith('business_agent_jobs'):return [dict(id=9,request_text=command,sender_id=77,chat_id=CHAT,tool_trace=[dict(name='china_saved_question',bot_id=BOT,reply_message_id=71)])]
    if path.startswith('analytics_snapshots'):return [dict(payload=dict(sid='seller'))]
    raise AssertionError(path)
   def tg(self,*args):return dict(status='member',user=dict(id=77,is_bot=False))
  return TestIO(),dict(sender_id=77,chat_id=CHAT,bot_id=BOT,job_id=9,reply_message_id=71,execution_kind=kind)
 def test_bid_alias_approved_by_arbitrary_current_human(self):
  io,a=self.make_io();io.validate_owner(a)
 def test_bid_alias_does_not_authorize_other_execution_types(self):
  io,a=self.make_io(kind='price')
  with self.assertRaises(ValueError):io.validate_owner(a)
 def test_modified_command_cannot_approve_original_plan(self):
  io,a=self.make_io(command='поднимай на50%')
  with self.assertRaises(ValueError):io.validate_owner(a)
 def test_left_member_denied_again_before_execution(self):
  io,a=self.make_io();io.tg=lambda *args:dict(status='left',user=dict(id=77,is_bot=False))
  with self.assertRaises(ValueError):io.validate_owner(a)

