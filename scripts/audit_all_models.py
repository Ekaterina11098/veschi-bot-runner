"""Read-only model inventory: no business APIs, no prompts, no credentials in output."""
import json,re,sys
from pathlib import Path
MODELS=re.compile(r'gpt[-_][0-9][a-zA-Z0-9_.-]*|o[134](?:-mini)?')
EXT={'.py','.js','.mjs','.ts','.yml','.yaml','.toml','.json','.txt','.md'}
for root in map(Path,sys.argv[1:]):
 count=0;matches=[]
 for p in sorted(root.rglob('*')):
  if not p.is_file() or p.suffix not in EXT or any(x in p.parts for x in ('.git','node_modules','recovery-output','recovery-vault','source')):continue
  if p.stat().st_size>2000000:continue
  count+=1
  for n,line in enumerate(p.read_text(encoding='utf-8',errors='replace').splitlines(),1):
   models=sorted(set(MODELS.findall(line)))
   if models:matches.append(dict(path=str(p.relative_to(root)),line=n,models=models))
 print(json.dumps(dict(root=str(root),scanned_files=count,matches=matches),ensure_ascii=False))
