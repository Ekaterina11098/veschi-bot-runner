"""Owner requested recovery of missing15:00 report: private cache only, no marketplace reads."""
import os
from datetime import datetime,timezone
from china_price_apply import IO
from china_advertising_midday import prepare_midday,unavailable_history_report,MSK
if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Public main required')
os.environ['WB_TOKEN_3']='disabled-cache-only'
io=IO();io.wb=lambda *a,**k:(_ for _ in ()).throw(RuntimeError('WB calls forbidden in cached recovery'))
day=datetime.now(MSK).date().isoformat()
if day!='2026-11-11':raise ValueError('Owner oneoff expired')
source=io.get('china_agent:advertising_midday_inclusive:'+day+':v1')
if not source or not source.get('batches')or source.get('day')not in (None,day):raise ValueError('Current source unavailable')
observed=source.get('completed_at',source['observed_at'])
age=(datetime.now(timezone.utc)-datetime.fromisoformat(observed.replace('Z','+00:00'))).total_seconds()
if not 0<=age<=4800:raise ValueError('Cached source too old')
prepared=prepare_midday(io,day,source,observational_only=True)
unavailable_history_report(io,day,source,prepared,ValueError('Completed-day campaign history unavailable: expected list for 41756218'))
