"""Owner-selected scheduled report checks without any model transport."""
import copy
POLICY='china_agent:advertising_midday_review_policy:v1'
def enabled(io):
 p=io.get(POLICY)or{}
 return p.get('enabled')is True and p.get('mode')=='full_checks_no_model'and p.get('cabinet')=='token_3'and p.get('chat_id')==-1004342917488 and p.get('owner_id')==5122667182 and p.get('paid_api_allowed')is False
def review(bundle,source):
 """Preserve every fully checked action; unknown evidence never becomes an action."""
 if source.get('day_quality',{}).get('usable')is not True:raise ValueError('Completed-day source unavailable')
 if source.get('full_growth_review',{}).get('status')!='complete':raise ValueError('Full catalogue checks incomplete')
 if bundle.get('economic_review_complete')is not True:raise ValueError('Economic checks incomplete')
 directions=bundle.get('recommendation_directions')or{}
 if set(directions)!={'raise','add','reduce','exclude'}:raise ValueError('All four directions must be checked')
 unresolved=[r for r in directions['add'].get('rows',[])if r.get('ready')is not True]
 if unresolved:raise ValueError('Addition validation unfinished: '+','.join(str(r.get('nm_id'))for r in unresolved))
 out=copy.deepcopy(bundle)
 for c in out['campaigns']:
  for r in c.get('focus',[])+c.get('attention',[]):
   if r.get('action')and(r.get('data_blocker')or r.get('pending_first_day')or r.get('already_excluded')):raise ValueError('Unready action survived')
 out.pop('codex_analysis',None)
 out['midday_review']=dict(backend='owner_selected_full_checks_no_model',validation_revision='ready_candidates_v2',full_catalogue_checked=True,economics_checked=True,completed_period_to=source['period_to'],source_ref=source['full_growth_review']['input_key'],model_calls=0,wb_writes=0)
 return out

