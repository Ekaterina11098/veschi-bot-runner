"""Owner-approved handling of a brand-new campaign whose WB statistics are not yet formed."""
from datetime import date
POLICY='china_agent:morning_new_campaign_reporting:v1'
def attach(io,bundle):
 p=io.get(POLICY)or{}
 if not(p.get('enabled')is True and p.get('owner_id')==5122667182 and p.get('cabinet')=='token_3'):return bundle
 end=bundle['days'][-1]
 for c in bundle['campaigns']:
  if c.get('status')!=9 or c.get('created')!=end or c.get('period')is not None or c.get('last')is not None:continue
  if c['id']not in p.get('campaign_ids',[]):continue
  bundle.setdefault('approved_statistics_exceptions',{})[str(c['id'])]=dict(owner_id=5122667182,owner_accepted_separate_row=True,reason='new_campaign_no_wb_statistics',policy_key=POLICY)
  c['owner_statistics_note']='Новая РК от'+date.fromisoformat(end).strftime('%d.%m')+'. Первый полный день — сегодня; оценка после его завершения. Без изменений.'
 return bundle
