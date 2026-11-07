"""Read-only inventory of Codex-product auth versus ordinary API calls. Never print secrets or source lines."""
import json,re
from pathlib import Path
EXT={'.py','.js','.mjs','.cjs','.ts','.tsx','.yml','.yaml','.toml','.json','.sh','.ps1','.bat','.cmd'}
SKIP={'.git','node_modules','__pycache__','.venv','venv','recovery-output','recovery-vault','private-audit'}
PATTERNS={
 'codex_cli':r'(?i)(?:\bcodex(?:\.exe)?[ \\t]+(?:exec|app-server|mcp-server|login|--))',
 'codex_sdk_or_action':r'(?i)@openai/codex|openai/codex-action|from[ \\t]+codex_sdk|new[ \\t]+Codex[ \\t]*\\(',
 'codex_product_endpoint':r'(?i)backend-api/codex|api\\.openai\\.com/v1/codex',
 'api_key_auth_override':r'(?i)forced_login_method[ \\t]*=[ \\t]*[\"\x27]api|--with-api-key|CODEX_API_KEY',
 'agents_api_sessions':r'(?i)beta\\.agents\\.sessions|/v1/agents/sessions',
 'responses_api':r'(?i)responses\\.create|/v1/responses',
 'chat_completions_api':r'(?i)chat\\.completions|/v1/chat/completions',
}
# Keep explicit patterns simple and compile after constructing the source.
PATTERNS={
 'codex_cli':r'(?i)\bcodex(?:\.exe)?\s+(?:exec|app-server|mcp-server|login|--)',
 'codex_sdk_or_action':r'(?i)@openai/codex|openai/codex-action|from\s+codex_sdk|new\s+Codex\s*\(',
 'codex_product_endpoint':r'(?i)backend-api/codex|api\.openai\.com/v1/codex',
 'api_key_auth_override':r'(?i)forced_login_method\s*=\s*[\"\x27]api|--with-api-key|CODEX_API_KEY',
 'agents_api_sessions':r'(?i)beta\.agents\.sessions|/v1/agents/sessions',
 'responses_api':r'(?i)responses\.create|/v1/responses',
 'chat_completions_api':r'(?i)chat\.completions|/v1/chat/completions',
}
patterns={k:re.compile(v)for k,v in PATTERNS.items()}
out=[]
for label,root in [('runner',Path('.')),('private_default',Path('private-audit'))]:
 found=[];count=0
 for p in sorted(root.rglob('*')):
  rel=p.relative_to(root)
  if not p.is_file()or p.suffix not in EXT or any(x in SKIP for x in rel.parts)or p.stat().st_size>2000000:continue
  count+=1
  for n,line in enumerate(p.read_text(encoding='utf-8',errors='replace').splitlines(),1):
   kinds=[k for k,v in patterns.items()if v.search(line)]
   if kinds:found.append({'path':str(rel),'line':n,'kinds':kinds,'test_or_fixture':bool(re.search(r'(^|/)(?:test[^/]*|tests|fixtures)(/|_|\.)',str(rel)))})
 out.append({'root':label,'files_scanned':count,'matches':found})
print('CODEX_ACCESS_AUDIT='+json.dumps(out,separators=(',',':'),ensure_ascii=True))
