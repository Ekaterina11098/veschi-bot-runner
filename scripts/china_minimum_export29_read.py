"""Read-only official WB minimum XLSX export using saved server browser; no uploads."""
import asyncio,base64,hashlib,os,re,tempfile
from datetime import datetime,timezone
import requests
from playwright.async_api import async_playwright
from china_cloud_cost_control import Cache
ROOT='china_agent:minimum_browser_export:2026-10-29:v2'
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
   e['phase']='seller'
   if not await page.get_by_text('VESCHI LIMITED',exact=True).first.is_visible():
    current=page.get_by_text(re.compile(r'^ИП Лазарев П')).filter(visible=True).first
    await current.click(timeout=15000)
    await page.get_by_text('VESCHI LIMITED',exact=True).filter(visible=True).last.click(timeout=15000)
    await page.wait_for_timeout(4000)
   if not await page.get_by_text('VESCHI LIMITED',exact=True).first.is_visible():raise ValueError('China seller not visible')
   await page.goto('https://seller.wildberries.ru/discount-and-prices/main-table?search=1473244991',wait_until='domcontentloaded',timeout=60000)
   await page.wait_for_timeout(5000)
   e['phase']='excel_menu';c.put(ROOT,e)
   await page.get_by_role('button',name=re.compile(r'^(Actions|Действия)$')).click(timeout=15000)
   await page.get_by_text('Excel',exact=True).click(timeout=15000)
   await page.get_by_text(re.compile(r'Smart Promo Minimum Price and Blocking|Минимальная цена.*блок',re.I)).click(timeout=15000)
   dialog=page.get_by_role('dialog')
   e['dialog_text']=(await dialog.inner_text(timeout=10000))[:12000]
   e['buttons']=await dialog.get_by_role('button').all_text_contents()
   e['phase']='download';c.put(ROOT,e)
   button=dialog.get_by_role('button',name=re.compile(r'Download.*template|Скачать.*шаблон|Download.*Excel|Скачать.*Excel',re.I))
   if await button.count()!=1:raise ValueError('Download button not uniquely identified')
   async with page.expect_download(timeout=45000) as info:await button.click()
   download=await info.value
   path=os.path.join(tempfile.gettempdir(),'minimum-baseline29.xlsx');await download.save_as(path)
   raw=open(path,'rb').read()
   if not raw.startswith(b'PK') or len(raw)>3000000:raise ValueError('Export is not a bounded XLSX')
   e.update(status='exported',observed_at=stamp(),sha256=hashlib.sha256(raw).hexdigest(),b64=base64.b64encode(raw).decode(),file_name=download.suggested_filename,source='WB_seller_cabinet_export',seller_name=cfg['seller_name'],seller_ui_id=cfg['seller_ui_id'],currency=cfg['currency'])
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
