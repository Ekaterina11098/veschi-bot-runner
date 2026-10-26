"""Read-only reconcile known created draft; never create or mutate."""
import json
from datetime import datetime,timezone
from china_cloud_cost_control import Cache,WB,validate_identity
c=Cache();w=WB();validate_identity(c,w)
cs=w.campaigns([41332083,41325637])
budgets=w.req('/api/advert/v2/budget','POST',dict(advertIds=[41332083,41325637]))
c.put('china_agent:codex_search_expand26:v3:reconciliation',dict(status='observed',observed_at=datetime.now(timezone.utc).isoformat(),campaigns=cs,budgets=budgets,wb_writes=0))
print('Existing draft and target readback saved; zero writes.')
