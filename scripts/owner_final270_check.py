"""Owner-authorized full check. Review only, no Telegram or WB mutations."""
from china_loss_execute import IO
from china_new_ad_reports import source,process_requests
from china_proposal_final_review import complete
io=IO()
req=dict(io.get('china_agent:new_ad_report_request:v1:270')or{},revision='final-v3',maximum_count=50,subject_ids=[50])
s,groups,review,key=complete(io,source(io),req)
print({'status':review['status'],'counts':review['counts'],'scope':review['scope_count'],'ready':sum(map(len,groups.values())),'review_key':key,'telegram_sends':0,'wb_writes':0})

# Only a fully completed check may become a user-facing final plan.
key='china_agent:new_ad_report_request:v1:270'
old=io.get(key)or{}
if old.get('revision')!='final-v3':
 archive=key+':archive:before-final-v3'
 if not io.get(archive):io.create(archive,old)
 io.put(key,dict(old,status='pending',revision='final-v3',maximum_count=50,final_checks_required=True,owner_final_source='Owner requested completed checks before final offer, no intermediate results'))
elif old.get('status')not in('pending','done'):
 raise RuntimeError('Previous final delivery unresolved; no blind retry')
if (io.get(key)or{}).get('status')!='done':
 process_requests(io,job_id=270)
result=io.get(key)or{}
print({'final_status':result.get('status'),'plan_id':result.get('plan_id'),'wb_writes':0})
if result.get('status')!='done':raise RuntimeError('Final proposal not delivered; inspect exact blocker without resending')
