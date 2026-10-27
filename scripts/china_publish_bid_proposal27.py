"""Publish one checked proposal requested by owner; never execute marketplace writes."""
import os,json,copy
from datetime import datetime,timezone
from urllib.parse import urlencode
from china_price_apply import IO
from conversion_watches import Worker,RECEIPTS,question_marker
import china_bid_proposals as q
import china_advertising_plans as p
import china_cloud_cost_control as cloud
KEY='owner-checked-bid-proposal27:139:0'
REQUEST='china_agent:bid_proposals:current_request:2026-10-27:v2'
RESULT='china_agent:bid_proposals:current_result:2026-10-27:v1'
class ReadWB(cloud.WB):
 def req(self,path,method='GET',body=None,write=False):
  if write:raise PermissionError('Proposal cannot change WB')
  return super().req(path,method,body,write=False)
def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main' or datetime.now(timezone.utc).date().isoformat()!='2026-10-27':raise ValueError('Dated public main only')
 io=IO();cloud.WB=ReadWB
 def db(method,table,params=None,body=None,prefer=None):
  if table not in ['telegram_api_cache','business_agent_config','business_agent_jobs']:raise PermissionError('DB scope')
  if table!='telegram_api_cache' and method!='GET':raise PermissionError('Original jobs immutable')
  return io.db(table+('?' +urlencode(params) if params else ''),method,body,prefer)
 def transport(chat,text):
  if chat!=-1004342917488:raise PermissionError('Wrong chat')
  return dict(ok=True,result=io.tg('sendMessage',dict(chat_id=chat,text=text,disable_web_page_preview=True,reply_parameters=dict(message_id=question_marker(job)['message_id'],allow_sending_without_reply=True))))
 w=Worker(db,transport)
 cfg=w.config()
 if cfg['chat_id']!=-1004342917488 or cfg['bot_id']!=8780468043:raise PermissionError('Registration mismatch')
 if io.tg('getMe',{})['id']!=8780468043:raise PermissionError('Bot mismatch')
 w.member_check=lambda actor:io.tg('getChatMember',dict(chat_id=cfg['chat_id'],user_id=actor))
 request=w.get(REQUEST)
 if not request or request.get('authorized_by')!=5122667182 or request.get('wb_execution_authorized') is not False:raise ValueError('Owner proposal request absent')
 jobs=db('GET','business_agent_jobs',params=dict(id='eq.'+str(request['job_id']),agent_id='eq.china',chat_id='eq.-1004342917488',select='*'))
 if len(jobs)!=1:raise ValueError('Original question missing')
 job=jobs[0]
 prior=w.get(RECEIPTS+KEY)
 if prior:
  if prior['status']=='sent':
   plan=w.get(p.P+'dialog-ads-'+str(job['id'])+'-raise')
   if plan:p.bind(w,plan['text'],prior['message_id'])
  print(json.dumps(dict(status=prior['status'],message_id=prior.get('message_id'),resent=False)));return
 result=q.prepare(w,job,request['nm_ids'],raise_percent=request['raise_percent'],count=30)
 if result['status']!='ready':
  w.save(RESULT,dict(status='blocked',reason=result.get('note'),blocked=result.get('blocked'),wb_writes=0));print(json.dumps(dict(status='blocked')));return
 plan=w.get(p.P+result['plan_id'])
 if set(i['nm_id'] for i in plan['items'])-set(request['nm_ids']):raise ValueError('Unexpected candidates')
 fresh=w.get('china_agent:bid_proposal_source:v1:'+str(job['id']))
 stats={int(k):v for k,v in fresh['stats'].items()}
 lines=['Павел, после проверки предлагаю '+str(len(plan['items']))+' дополнительных теста ставок (+20%, округление WB). До 30 обоснованных товаров сейчас не набирается: остальные уже менялись, не прошли экономику или статистику.']
 for i in plan['items']:
  r=i['evidence'];ec=i['economics'];ds=q.daily(stats[i['campaign_id']],i['nm_id'])
  full=['2026-10-24','2026-10-25','2026-10-26']
  available=[d for d in full if d in ds];v={k:sum(ds[d][k] for d in available) for k in ['spend','amount','orders','clicks']}
  dr=format(v['spend']/v['amount']*100,'.2f')+'%' if v['amount'] else 'нет заказов'
  t=r['today'];td=format(r['today_drr'],'.2f')+'%' if r['today_drr'] is not None else 'нет заказов'
  lines+=['',i['article']+' · РК '+str(i['campaign_id'])+' · рекомендации: '+format(i['old_minor']/100,'.2f')+' → '+format(i['target_minor']/100,'.2f')+' ¥.',
  '24–26.10: расход '+format(v['spend'],'.2f')+' ¥; '+str(v['orders'])+' заказов; ДРР '+dr+'. Сегодня: '+format(t['spend'],'.2f')+' ¥; '+str(t['orders'])+' заказов; ДРР '+td+'.',
  'Решение по полному 26.10 после изменения 25.10: ДРР '+str(r['previous_drr'])+'%. Выкуп '+str(ec['paid'])+'/'+str(ec['finished'])+'; предварительно при ДРР5% +'+str(ec['expected_cny_at5'])+' ¥/заказ.']
 lines+=['','Малая выборка: по 1 рекламному заказу, результат теста не гарантирован. Ставки уже повышенных сегодня товаров повторно не трогаем. Срез '+datetime.fromisoformat(fresh['observed_at']).astimezone(q.MSK).strftime('%d.%m %H:%M')+' МСК.',
 'Экономика предварительная: своя себестоимость/выкуп, историческая логистика; курс12₽/¥, налог5%, обработка10₽ — допущения; общие удержания могут быть неполны.',
 '20 ¥ дополнительного расхода на товар — ориентир повторной оценки, не технический лимит. Цель ДРР5%, гарантии нет. Пополнений и пауз нет.',
 'Ответьте «делай» или «поднимай» именно на это сообщение — агент выполнит только эти ставки и проверит результат WB.',
 'План рекламы: '+plan['plan_id']]
 plan['text']='\n'.join(lines)
 if len(plan['text'])>4000:raise ValueError('Proposal too long')
 plan.pop('delivery_text',None);plan.pop('proposal_files',None)
 w.save(p.P+plan['plan_id'],plan)
 receipt=dict(status='sending',chat_id=cfg['chat_id'],text=plan['text'],created_at=datetime.now(timezone.utc).isoformat())
 if not w.save(RECEIPTS+KEY,receipt,insert=True):raise ValueError('Delivery identity already exists')
 try:
  sent=transport(cfg['chat_id'],plan['text'])['result']
  if sent.get('chat',{}).get('id')!=cfg['chat_id'] or type(sent.get('message_id')) is not int:raise ValueError('Telegram receipt scope')
  receipt.update(status='sent',message_id=sent['message_id']);w.save(RECEIPTS+KEY,receipt);p.bind(w,plan['text'],sent['message_id'])
 except Exception:
  receipt['status']='uncertain';w.save(RECEIPTS+KEY,receipt);raise
 outcome=receipt['status']
 w.save(RESULT,dict(status=outcome,plan_id=plan['plan_id'],plan_sha256=plan['plan_sha256'],items=[dict(article=i['article'],old_minor=i['old_minor'],target_minor=i['target_minor'],campaign_id=i['campaign_id']) for i in plan['items']],message_id=receipt.get('message_id'),chat_id=cfg['chat_id'],bot_id=cfg['bot_id'],wb_writes=0,observed_at=datetime.now(timezone.utc).isoformat()))
 print(json.dumps(dict(status=outcome,items=len(plan['items']),message_id=receipt.get('message_id'),wb_writes=0)))
if __name__=='__main__':main()
