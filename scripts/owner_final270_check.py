"""Owner-authorized full check. Review only, no Telegram or WB mutations."""
from china_loss_execute import IO
from china_new_ad_reports import source
from china_proposal_final_review import complete
io=IO()
req=dict(io.get('china_agent:new_ad_report_request:v1:270')or{},revision='final-v3',maximum_count=50,subject_ids=[50])
s,groups,review,key=complete(io,source(io),req)
print({'status':review['status'],'counts':review['counts'],'scope':review['scope_count'],'ready':sum(map(len,groups.values())),'review_key':key,'telegram_sends':0,'wb_writes':0})
