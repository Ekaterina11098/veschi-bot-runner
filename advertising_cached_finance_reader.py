"""Bounded lazy daily finance history reader; values/formula/history unchanged."""
def install(stage):
 original=stage.snapshots
 def snapshots(read,sources,cabinet,start=None,end=None):
  if tuple(sources)!=('mpstats_lk_wb_products',) or start is None or str(start)!=str(end):
   return original(read,sources,cabinet,start,end)
  def daily():
   # Fetch light version IDs first; load one payload at a time. Consumers stop
   # after their first usable version, retaining a fallback without loading1000.
   params=dict(source='eq.mpstats_lk_wb_products',cabinet='eq.'+cabinet,status='eq.complete',
    period_from='eq.'+str(start),period_to='eq.'+str(end),select='id',order='id.desc',limit=5)
   markers=read('analytics_snapshots',params) or []
   for marker in markers:
    rows=read('analytics_snapshots',dict(id='eq.'+str(marker['id']),select='id,source,cabinet,payload,collected_at,period_from,period_to',limit=1)) or []
    for row in rows:yield row
  return daily()
 stage.snapshots=snapshots
