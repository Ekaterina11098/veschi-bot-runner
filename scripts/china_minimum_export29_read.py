"""Read-only official WB minimum XLSX export using saved server browser; no uploads."""
import asyncio,base64,hashlib,os,re,tempfile
from datetime import datetime,timezone
import requests
from playwright.async_api import async_playwright
from china_cloud_cost_control import Cache
ROOT='china_agent:minimum_browser_export:2026-10-29:diagnostic:v1'
def stamp():return datetime.now(timezone.utc).isoformat()
async def main():
 if os.environ.get('GITHUB_REPOSITORY')!='Ekaterina11098/veschi-bot-runner' or os.environ.get('GITHUB_REF')!='refs/heads/main':raise ValueError('Registered main only')
 c=Cache();cfg=c.get('china_agent:minimum_browser:profile:v1');e=c.get(ROOT)
 if e:print(e['status']);return
 if not cfg or cfg.get('seller_name')!='VESCHI LIMITED' or not os.environ.get('TINYFISH_API_KEY'):raise ValueError('Server configuration missing')
 e=dict(status='starting',created_at=stamp(),wb_writes=0,uploads=0,minimum_writer_enabled=False)
 if not c.create(ROOT,e):raise ValueError('Existing export')
 h={'X-API-Key':os.environ['TINYFISH_API_KEY']};url='https://agent.tinyfish.ai/v1/profiles/'+cfg['profile_id'];session=None
 try:
  response=requests.post(url+'/setup-session',headers=h,json={'url':'https://seller.wildberries.ru/discount-and-prices/main-table?search=1473244991','timeout_seconds':600},timeout=60)
  if not response.ok:raise RuntimeError('Setup HTTP '+str(response.status_code))
  session=response.json();e.update(status='reading',phase='connect');c.put(ROOT,e)
  async with async_playwright() as p:
   browser=await p.chromium.connect_over_cdp(session['cdp_url'],timeout=45000)
   context=browser.contexts[0];page=context.pages[0] if context.pages else await context.new_page()
   await page.goto('https://seller.wildberries.ru/discount-and-prices/main-table?search=1473244991',wait_until='domcontentloaded',timeout=60000)
   await page.wait_for_timeout(7000)
   e['phase']='initial_page'
   text=await page.locator('body').inner_text(timeout=15000)
   e.update(status='diagnostic_complete',page_url=page.url,initial_text=re.sub(r'\\+7[\\s()0-9-]{9,}', '[phone]',text[:6500]),observed_at=stamp())
   c.put(ROOT,e)
   await browser.close()
 except Exception as ex:
  e.update(status='blocked',error_type=type(ex).__name__,completed_at=stamp())
  try:e['visible_buttons']=[x[:150] for x in await page.get_by_role('button').filter(visible=True).all_text_contents()][:60]
  except Exception:pass
  if isinstance(ex,(ValueError,RuntimeError)):e['reason']=str(ex)
  c.put(ROOT,e)
 finally:
  if session and session.get('session_id'):
   try:
    r=requests.post(url+'/setup-session/cancel',headers=h,json={'session_id':session['session_id']},timeout=30)
    e['setup_closed']=r.ok;c.put(ROOT,e)
   except requests.RequestException:pass
 print(e['status'])
if __name__=='__main__':asyncio.run(main())
