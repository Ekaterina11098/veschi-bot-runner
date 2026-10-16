"""Install China-only order coverage overlays on the existing pinned checkout."""
from pathlib import Path
import shutil
root=Path(__file__).resolve().parent
for name in ('order_coverage','wb_order_gaps','coverage_worker'):
    shutil.copyfile(root/('china_'+name+'.py'),Path('china_agent')/(name+'.py'))
path=Path('china_agent/demand.py')
code=path.read_text()
replacements=[
 ("if p['sales']>0 and p['nm_id'] is not None","if p.get('sales') is not None and p['sales']>0 and p['nm_id'] is not None",1),
 ("key=lambda p: (p['sales'], p['orders'])","key=lambda p: (p.get('sales') is not None, p.get('sales') or 0, p['orders'])",2),
]
for before,after,n in replacements:
    if code.count(before)==n:
        code=code.replace(before,after)
    elif code.count(after)!=n:
        raise RuntimeError('Unexpected China demand implementation; nullable sales patch not applied')
path.write_text(code)
