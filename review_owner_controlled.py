"""Approved one-pass reviews: two exact items, WB GET only, durable drafts and new notices."""
import os,json,time,hashlib,contextlib,io
from datetime import datetime,timezone
import requests
from stock_deploy_support import seal,error
from review_durable_workflow import DurableReviews,digest,generate_and_persist
from review_queue import _request
from review_inbox_cache import load_inbox
from refresh_review_inbox import fresh_today
from review_scope import reply_key
import wildberries as wb
BATCH='reviews-controlled-20261015-afde6671'
VERSION='owner-20261015-afde6671-v1'
TARGETS=[('token_1','ООО','soHH5MsaEY08FASqdqtM','548-GloriaBag-brown'),('token_2','ИП','PwB5eXmFztbgyBhGctsP','68-4belts115-black')]
EXPECTED_DESTINATION='96e17776da8ff52452990c88c38f1a2d4db9a4bf61f816e852a6ca65e946ea76'
SOURCE='1b4201067880e379d8dacbe5f6ca3f9848d6ffb0'
report={'source_commit':SOURCE,'batch':BATCH,'items':[],'wb_writes':0,'old_queues_processed':0,'telegram_attempts':0}
store=DurableReviews(_request)
original_request=requests.sessions.Session.request
def guarded(self,method,url,*args,**kwargs):
    method=method.upper()
    if 'wildberries.ru' in url and method!='GET':raise RuntimeError('WB writes forbidden')
    if url.startswith(os.environ['SUPABASE_URL'].rstrip('/')+'/rest/v1/'):
        path=url.split('/rest/v1/',1)[1].split('?')[0]
        if path not in ('telegram_api_cache','review_replies','review_benchmarks','review_inbox_cache'):raise RuntimeError('Unapproved backend path')
        if path!='telegram_api_cache' and method!='GET' and not(path=='review_replies' and method=='PATCH'):raise RuntimeError('Review publication queue writes forbidden')
    return original_request(self,method,url,*args,**kwargs)
requests.sessions.Session.request=guarded
def checkpoint():seal('reviews-controlled',report)
def tg(method,payload):
    response=requests.post('https://api.telegram.org/bot'+os.environ['TELEGRAM_BOT_TOKEN']+'/'+method,json=payload,timeout=(5,20))
    if not response.ok:raise RuntimeError('Telegram HTTP '+str(response.status_code))
    value=response.json()
    if value.get('ok') is not True:raise RuntimeError('Telegram did not confirm method')
    return value['result']
def sender(chat,text):
    if str(chat)!=os.environ['TELEGRAM_ALLOWED_CHAT_ID']:raise RuntimeError('Destination mismatch')
    report['telegram_attempts']+=1
    return tg('sendMessage',{'chat_id':chat,'text':text})['message_id']
@wb.scoped
def observe(item_id):
    response=wb.request_wb(wb.BASE_URL+'/api/v1/feedback',params={'id':item_id})
    value=response.json()
    if not isinstance(value,dict) or value.get('error') is True:raise RuntimeError('WB item not verified')
    item=value.get('data')
    if not isinstance(item,dict) or str(item.get('id'))!=item_id:raise RuntimeError('Exact WB item not verified')
    answer=item.get('answer')
    if answer is not None and (not isinstance(answer,dict) or not isinstance(answer.get('text'),str)):raise RuntimeError('Unknown WB answer')
    return item,(answer or {}).get('text','')
def main():
    batch_key='reviews:controlled-run:'+BATCH
    previous=store.read(batch_key)
    if previous:raise RuntimeError('Controlled pass already claimed; inspect journal before any continuation')
    cutover=datetime.now(timezone.utc).isoformat()
    store.insert(batch_key,{'batch':BATCH,'source':SOURCE,'run_id':os.environ['GITHUB_RUN_ID'],'created_at':cutover,'status':'started'})
    bot=tg('getMe',{})
    chat=tg('getChat',{'chat_id':os.environ['TELEGRAM_ALLOWED_CHAT_ID']})
    fingerprint=hashlib.sha256((str(chat['id'])+'|'+str(bot['id'])).encode()).hexdigest()
    if fingerprint!=EXPECTED_DESTINATION or chat.get('type')!='private':raise RuntimeError('Old verified Telegram destination changed')
    report['telegram_destination_verified']=True
    import openai_client as generation
    from openai import OpenAI
    generation.OpenAI=lambda **kw:OpenAI(timeout=90,max_retries=0,**kw)
    for cabinet,name,item_id,article in TARGETS:
        result={'cabinet':cabinet,'cabinet_name':name,'id':item_id,'article':article,'version':VERSION}
        report['items'].append(result)
        try:
            items,stamp=load_inbox('feedbacks',cabinet=cabinet)
            candidates=[x for x in (items or []) if str(x.get('id'))==item_id]
            if len(candidates)!=1 or not fresh_today(stamp):raise RuntimeError('Approved source cache missing or stale')
            saved_item=candidates[0]
            if saved_item.get('productDetails',{}).get('supplierArticle')!=article:raise RuntimeError('Approved article mismatch')
            pause=wb.review_pause_seconds(cabinet=cabinet)
            if pause:raise wb.ReviewRateLimit(pause)
            actual,actual_answer=observe(item_id,cabinet=cabinet)
            actual_article=(actual.get('productDetails') or {}).get('supplierArticle')
            if actual_article and actual_article!=article:raise RuntimeError('Fresh WB article mismatch')
            result['preflight_at']=datetime.now(timezone.utc).isoformat()
            result['preflight_sha256']=digest(actual)
            if actual_answer.strip():
                key=reply_key(item_id,cabinet,'feedbacks')
                rows=_request('GET','/review_replies',params={'feedback_id':'eq.'+key,'select':'state','limit':1}) or []
                if rows:store.close_manual(key,actual_answer,result['preflight_at'])
                else:store.insert('reviews:manual-observed:'+digest([key,VERSION]),{'cabinet':cabinet,'kind':'feedbacks','id':item_id,'actual_answer':actual_answer,'actual_answer_sha256':digest(actual_answer),'observed_at':result['preflight_at'],'status':'manual_confirmed'})
                result['status']='manual_answer_present'
                checkpoint();continue
            if actual.get('isAnswered') is True:raise RuntimeError('WB answered flag conflicts with empty answer')
            # Exact fresh WB item supplies buyer name/text/rating; cached product details only fill absent metadata.
            item=dict(actual)
            if not item.get('productDetails'):item['productDetails']=saved_item.get('productDetails',{})
            draft_key='reviews:draft:'+digest([reply_key(item_id,cabinet,'feedbacks'),VERSION])
            draft=store.read(draft_key)
            if draft:
                if draft['source_sha256']!=digest(item):raise RuntimeError('Draft source changed')
            else:
                generate_and_persist(store,item,cabinet,'feedbacks',VERSION,generation.generate_draft)
                draft=store.read(draft_key)
            if not draft or draft['confirmation_status']!='draft' or len(draft['variants'])!=2:raise RuntimeError('Durable pair not verified')
            result.update(status='draft_saved',draft_key=draft_key,source_sha256=draft['source_sha256'],variants=draft['variants'],draft_readback=True,confirmation_status='draft')
            checkpoint()
        except wb.ReviewRateLimit as exc:result.update(status='paused',retry_after=exc.retry_seconds)
        except Exception as exc:result.update(status='error',error=error(exc))
        finally:checkpoint()
    # Notify only results CREATED by this controlled pass, never claim old queues.
    for result in report['items']:
        if result['status']=='draft_saved':
            text='Отзывы · '+result['cabinet_name']+' · '+result['article']+'\nЧерновики сохранены, в WB не отправлены.\n\nВариант 1:\n'+result['variants'][0]+'\n\nВариант 2:\n'+result['variants'][1]+'\n\nДля публикации требуется отдельное подтверждение выбранного текста.'
        elif result['status']=='manual_answer_present':
            text='Отзывы · '+result['cabinet_name']+' · '+result['article']+'\nОтвет уже опубликован в WB вручную. Повторная публикация и новые черновики не выполнялись.'
        else:
            text='Отзывы · '+result['cabinet_name']+' · '+result['article']+'\nПодготовка не завершена; ответы в WB не отправлялись.'
            if result.get('retry_after'):text+=' Повтор проверки возможен не раньше чем через '+str(result['retry_after'])+' секунд.'
        if len(text)>4000:raise RuntimeError('Notice too long; durable drafts retained, do not truncate')
        notice_key,notice=store.prepare_notice(BATCH+':'+result['cabinet']+':'+result['id'],os.environ['TELEGRAM_ALLOWED_CHAT_ID'],text,cutover,cutover)
        result['notice_key']=notice_key
        checkpoint()
        result['delivery_status']=store.deliver_notice(notice_key,sender,enabled=True)
        result['notice_readback']=store.read(notice_key)
        checkpoint()
    report['complete']=all(x['status'] in ('draft_saved','manual_answer_present') for x in report['items'])
    _request('PATCH','/telegram_api_cache',params={'cache_key':'eq.'+batch_key},payload={'payload':{'batch':BATCH,'source':SOURCE,'run_id':os.environ['GITHUB_RUN_ID'],'created_at':cutover,'status':'complete' if report['complete'] else 'incomplete','item_states':[{k:r[k] for k in ('cabinet','id','status')} for r in report['items']]}},prefer='return=representation')
hidden=io.StringIO()
try:
    with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):main()
except BaseException as exc:report['error']=error(exc)
finally:
    try:
        with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):
            report['durable_backup']=_request('GET','/telegram_api_cache',params={'or':'(cache_key.like.reviews:draft:*,cache_key.like.reviews:approval:*,cache_key.like.reviews:manual-history:*,cache_key.like.reviews:manual-observed:*,cache_key.like.reviews:notice:*,cache_key.like.reviews:controlled-run:*)','select':'cache_key,payload,updated_at,expires_at','order':'cache_key.asc','limit':2000}) or []
            report['backup_manifest']=[{'key':r['cache_key'],'payload_sha256':digest(r['payload'])} for r in report['durable_backup']]
            report['backup_required_prefixes']=['reviews:draft:','reviews:approval:','reviews:manual-history:','reviews:manual-observed:','reviews:notice:','reviews:controlled-run:']
    except Exception as exc:report['backup_error']=error(exc)
    report['private_log']=hidden.getvalue()
    checkpoint()
    print(json.dumps({'complete':report.get('complete',False),'draft_pairs':sum(x.get('status')=='draft_saved' for x in report['items']),'confirmed_notices':sum(x.get('delivery_status')=='confirmed' for x in report['items']),'wb_writes':0,'old_queues_processed':0,'error_type':report.get('error',{}).get('type')}))
