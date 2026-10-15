"""One owner-scoped stock run. All business details are sealed; no generic dispatcher."""
import os,sys,json,time,hashlib,contextlib,io,base64,re
from pathlib import Path
from urllib.parse import urlparse
import psycopg
from stock_deploy_support import *
def load_authorization():
    import struct
    from cryptography.hazmat.primitives import serialization,hashes
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    from cryptography.hazmat.primitives.asymmetric import padding
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
    raw=(ROOT/'receiver/receiver-private.pem.aes').read_bytes()
    assert hashlib.sha256(raw).hexdigest()=='e315bdaf4bcc4ced0733a46a0a6d51c7e352d06fdb1d8ff3f65d51148fe8241e'
    magic=b'VESCHI-BACKUP-1\n';offset=len(magic);assert raw[:offset]==magic
    length=struct.unpack('>I',raw[offset:offset+4])[0];offset+=4
    encoded=raw[offset:offset+length];offset+=length;header=json.loads(encoded)
    decode=lambda k:base64.b64decode(header[k])
    derived=HKDF(algorithm=hashes.SHA256(),length=32,salt=decode('salt'),info=b'veschi-recovery-worker-key-v1').derive(os.environ['SUPABASE_SECRET_KEY'].encode())
    key=AESGCM(derived).decrypt(decode('wrap_nonce'),decode('worker_key'),magic)
    dec=Cipher(algorithms.AES(key),modes.GCM(decode('nonce'),raw[-16:])).decryptor();dec.authenticate_additional_data(encoded)
    receiver=serialization.load_pem_private_key(dec.update(raw[offset:-16])+dec.finalize(),password=None)
    data=Path('recovery-input/2026-10-15/authorized-three.aes.json').read_bytes()
    assert hashlib.sha256(data).hexdigest()=='311b7e103d084de27f26ef0015ea0f0a77803cf5f51b4cd0ebed3da74140591d'
    envelope=json.loads(data)
    key=receiver.decrypt(base64.b64decode(envelope['receiver_wrapped_key']),padding.OAEP(mgf=padding.MGF1(hashes.SHA256()),algorithm=hashes.SHA256(),label=None))
    plain=AESGCM(key).decrypt(base64.b64decode(envelope['nonce']),base64.b64decode(envelope['ciphertext']),None)
    assert hashlib.sha256(plain).hexdigest()==envelope['plaintext_sha256']
    value=json.loads(plain)
    assert value['authorization']=='owner-controlled-first-three-20261015'
    assert len(value['allow'])==3 and len({x['article'] for x in value['allow']})==3
    return value
def card_ids(g,values,article):
    return [sorted([dict(nmID=c['nmID'],chrtIds=sorted([s.get('chrtID',s.get('chrtId')) for s in c.get('sizes',[])])) for c in cards if g.norm(c.get('vendorCode'))==article],key=lambda x:x['nmID']) for cards in values]
def main():
    report=dict(success=False,deployment_verified=True,execution_finished=False,wb_write_attempts=0,telegram_calls=0,other_queue_calls=0,results=[],source_commit='b1f54e3770fba9aabbe7773c2106fc6d56c92911',started=time.time())
    db=None;hidden=io.StringIO()
    try:
        deployment=json.loads((ROOT/'deployment-proof/deployment-summary.json').read_text())
        assert all(deployment.get(k) is True for k in ('success','limited_login_verified','committed_write_readback_verified','negative_privileges_verified','uncertain_lock_retained'))
        auth=load_authorization()
        assert os.environ['GITHUB_RUN_ATTEMPT']=='1'
        assert os.environ.get('LOCAL_WRITER_LOCK_HELD')=='true'
        db=runtime_db()
        with db.cursor() as cur:
            cur.execute("SELECT pg_try_advisory_lock(hashtext('veschi-stock-owner-global-writer'))")
            assert cur.fetchone()[0] is True
            # Stable owner authorization claim: no rerun, even under a new Actions run.
            cur.execute("SELECT snapshot,origin,created FROM stock_execution.stock_runs WHERE id=%s",(auth['authorization'],))
            previous=cur.fetchone()
            if previous is None:
                raise RuntimeError('Expected paused owner batch is missing')
            assert previous[1]=='technical-no-executor'
            old=json.loads((ROOT/'prior-controlled/controlled-summary.json').read_text())
            assert old.get('wb_write_attempts')==0 and old.get('confirmed')==0 and old.get('error_type')=='RateLimited' and old.get('not_executed')==3
            cur.execute("SELECT count(*) FROM stock_execution.stock_runs WHERE origin='cloud' AND created>=%s",(previous[2],))
            assert cur.fetchone()[0]==0,'New cloud activity requires reconciliation'
            claim=hashlib.sha256((auth['authorization']+':rate-limit-resume-1').encode()).hexdigest()
            cur.execute("INSERT INTO stock_execution.stock_events VALUES(%s,%s,NULL,%s,%s,%s) ON CONFLICT DO NOTHING",(claim,auth['authorization'],'technical_rate_limit_resume',time.time(),'{}'))
            assert cur.rowcount==1,'Continuation already claimed; no blind retry'
            cache_saved=json.loads(previous[0]).get('cache',{})
        db.commit()
        os.environ['STOCK_CLOUD_EXECUTION_ENABLED']='true'
        os.environ['STOCK_JOURNAL_IMPORT_ACCEPTED']='true'
        os.environ['STOCK_DATABASE_URL']=psycopg.conninfo.make_conninfo(host=HOST,port=5432,dbname='postgres',user=ROLE+'.'+PROJECT,password=password(),sslmode='require')
        os.environ['STOCK_STORAGE_PROOF_FILE']=str(ROOT/'current-job-storage-proof.json')
        os.environ['STOCK_STORAGE_PROOF_SCOPE']='owner-three:'+os.environ['GITHUB_RUN_ID']
        import stock_storage_health
        probe=dict(technical=True,scope=os.environ['STOCK_STORAGE_PROOF_SCOPE'],nonce=os.urandom(16).hex(),queued=False)
        def write(value):
            with db.transaction():
                with db.cursor() as cur:cur.execute('UPDATE stock_execution.stock_runs SET snapshot=%s WHERE id=%s',(json.dumps(value,sort_keys=True),auth['authorization']))
        def read():
            with db.cursor() as cur:
                cur.execute('SELECT snapshot FROM stock_execution.stock_runs WHERE id=%s',(auth['authorization'],));value=json.loads(cur.fetchone()[0])
            db.commit();return value
        stock_storage_health.verify_runtime_storage(write,read,probe)
        report['storage_proof_verified']=True
        import requests
        import tg_agent_new as g
        import auto_stock as a
        import stock_cloud_execution as cloud
        from stock_card_evidence import CardCatalog,catalog_evidence
        from stock_fbo import fbo_quantity
        g.RUN_DEADLINE=time.monotonic()+900
        g._CACHE_GET=lambda key:cache.get(key)
        def persist_cache(key,value,ttl):
            cache[key]=value
            write(dict(probe,cache=cache))
        cache=cache_saved;g._CACHE_SET=persist_cache
        g.cached_wb_metadata=lambda token,kind,ttl,loader:loader()
        original_api=g.api;current={'article':None,'allow_write':False,'location':None,'target':None}
        # Final independent HTTP fence, including any accidentally imported client.
        original_session=requests.sessions.Session.request
        def fenced(session,method,url,**kwargs):
            parsed=urlparse(url);host=parsed.hostname or '';path=parsed.path;m=method.upper()
            allowed=(host in ('api.moysklad.ru','online.moysklad.ru') and m=='GET' and path.startswith('/api/remap/1.2/'))
            allowed|=(host in ('common-api.wildberries.ru','common-api.wildberries.cn') and m=='GET' and path=='/api/v1/seller-info')
            allowed|=(host in ('content-api.wildberries.ru','content-api.wildberries.cn') and m=='POST' and path=='/content/v2/get/cards/list')
            allowed|=(host in ('statistics-api.wildberries.ru','statistics-api.wildberries.cn') and m=='GET' and path=='/api/v1/supplier/sales')
            allowed|=(host in ('marketplace-api.wildberries.ru','marketplace-api.wildberries.cn') and ((m=='GET' and path=='/api/v3/warehouses') or (m=='POST' and bool(re.fullmatch('/api/v3/stocks/[0-9]+',path)))))
            allowed|=(host in ('seller-analytics-api.wildberries.ru','seller-analytics-api.wildberries.cn') and ((m=='POST' and path=='/api/analytics/v1/stocks-report/wb-warehouses') or (m=='GET' and (path=='/api/v1/warehouse_remains' or bool(re.fullmatch('/api/v1/warehouse_remains/tasks/[0-9a-fA-F-]+/(status|download)',path))))))
            if m=='PUT' and host in ('marketplace-api.wildberries.ru','marketplace-api.wildberries.cn'):
                loc=current['location']
                allowed=bool(current['allow_write'] and loc and path=='/api/v3/stocks/'+str(loc['warehouse']) and kwargs.get('json')=={'stocks':[{'chrtId':loc['chrtId'],'amount':current['target']}]})
                if allowed:
                    # Pinned g.api validates/consumes committed journal intent before requests reaches this fence.
                    assert current['article'] in {x['article'] for x in auth['allow']}
                    assert report['wb_write_attempts']<3
                    current['allow_write']=False
                    report['wb_write_attempts']+=1
            if not allowed:raise RuntimeError('Unapproved network endpoint or write scope')
            return original_session(session,method,url,**kwargs)
        requests.sessions.Session.request=fenced
        g.required_tokens('MS_TOKEN','WB_TOKEN_1','WB_TOKEN_2','WB_TOKEN_3')
        with contextlib.redirect_stdout(hidden),contextlib.redirect_stderr(hidden):
            a.check_write_credentials()
            identities=[]
            for token in g.cabinet_tokens():
                info=g.api('GET','https://common-api.wildberries.ru/api/v1/seller-info',token)
                claims=json.loads(base64.urlsafe_b64decode(token.split('.')[1]+'==='))
                assert str(info.get('sid'))==str(claims['sid']),'Seller API/JWT mismatch'
                identities.append(info)
            assert len({x['sid'] for x in identities})==3
            report['seller_identity_verified']=True;report['identities']=identities
            # Direct fresh Moscow and direct same-day completed-window sales; no morning target replay.
            ms,unresolved=g.load_ms_stocks_dict()
            allcards=[];sales=[]
            for token in g.cabinet_tokens():
                cards=g.get_real_wb_cards_and_scores(token)
                for card in cards:card['_no_photo']=not bool(card.get('photos'))
                selected=CardCatalog([c for c in cards if g.norm(c.get('vendorCode')) in {x['article'] for x in auth['allow']}],catalog_evidence(cards))
                g.load_cabinet_fbo(token,selected)
                speed=g.fetch_sales_speed(token)
                sales.append(speed);allcards.append(selected)
                g.SALES_STATUS[token]={'available':True,'fetched_at':time.time(),'source':'direct-completed-seven-days'}
            for item in auth['allow']:
                art=item['article'];current.update(article=art,allow_write=False,location=None,target=None)
                result=dict(article=art,cabinet=g.CABINET_NAMES[item['cabinet']],approved_before=item['before'],approved_target=item['target'],written=False)
                report['results'].append(result)
                try:
                    with db.cursor() as cur:
                        cur.execute('SELECT owner_run FROM stock_execution.stock_sku_locks WHERE article=%s',(art,))
                        assert cur.fetchone() is None,'Article locked; no execution'
                    db.commit()
                    if art not in ms:
                        result.update(status='blocked_unknown_moscow');continue
                    locations,before=a.read_locations(art,allcards)
                    quantities=[{art:q} for q in before]
                    target=a.stock_plan(art,ms[art],allcards,quantities,sales)
                    fbo=[fbo_quantity(c,art,g.CheckError) for c in allcards]
                    daily=[{str(day):q for day,q in speed[1].get(art,{}).items()} for speed in sales]
                    original=item['snapshot']
                    differences=[]
                    checks={'moscow':(ms[art],original['moscow_source_stock']),'before':(before,[c['fbs'] for c in original['cabinets']]),'target':(target,item['expected_target']),'fbo':(fbo,[c['fbo'] for c in original['cabinets']]),'daily_sales':(daily,[c['daily_sales'] for c in original['cabinets']]),'card_ids':(card_ids(g,allcards,art),item['card_ids']),'eligible':([art in g.eligible_articles(c) for c in allcards],[c['eligible'] for c in original['cabinets']]),'locations':([cloud.location_scope(i,loc) for i,loc in enumerate(locations)],[c['location'] for c in original['cabinets']])}
                    for key,(new,old) in checks.items():
                        if new!=old:differences.append(key)
                    result.update(observed_at=time.time(),moscow=ms[art],current_fbs=before,target_fbs=target,fbo=fbo,daily_sales=daily,changed_inputs=differences,sum_fbs=sum(x for x in target if x is not None))
                    if differences:
                        result.update(status='stopped_changed_inputs_recalculated');continue
                    if ms[art]<15:
                        result.update(status='manual_only');continue
                    operations=[(i,b,t) for i,(b,t) in enumerate(zip(before,target)) if b!=t]
                    assert operations==[(item['cabinet'],item['before'],item['target'])],'Unapproved changes in recalculated article'
                    # Recheck immediately; pinned WBAdapter.guard also checks fresh cards/MSK/all FBS.
                    current.update(allow_write=True,location=cloud.location_scope(item['cabinet'],locations[item['cabinet']]),target=item['target'])
                    message=cloud.execute_article(g,a.read_locations,a.automatic_stock_plan,art,allcards,sales,ms,entry='owner-controlled-first-three')
                    result.update(status='confirmed',written=True,message=message)
                except BaseException as exc:
                    result.update(status='blocked_or_uncertain_no_retry',error=error(exc))
                    current['allow_write']=False
                    db.rollback()
            report['execution_finished']=True;report['success']=True
    except BaseException as exc:
        report['error']=error(exc)
        for item in (locals().get('auth') or {}).get('allow',[]):
            if item['article'] not in {x['article'] for x in report['results']}:report['results'].append(dict(article=item['article'],status='not_executed_preflight_failed',written=False))
    finally:
        report['ended']=time.time()
        if db:
            try:
                with db.cursor() as cur:
                    cur.execute("SELECT r.id,r.snapshot,o.seq,o.body,o.state FROM stock_execution.stock_runs r JOIN stock_execution.stock_operations o ON o.run=r.id WHERE r.origin='cloud' AND r.created>=%s",(report['started'],));report['journal_readback']=cur.fetchall()
                    cur.execute("SELECT count(*) FROM stock_execution.stock_sku_locks WHERE article='20-furbigscarf-khaki'");report['blocked_sku_lock_retained']=cur.fetchone()[0]==1
                db.commit()
            except BaseException as exc:report['journal_readback_error']=error(exc)
            db.close()
        text=hidden.getvalue()
        for name,value in os.environ.items():
            if len(value)>5 and any(x in name for x in ('TOKEN','PASSWORD','SECRET','DATABASE_URL')):text=text.replace(value,'[redacted]')
        report['private_log']=text
        seal('controlled',report)
        public=dict(success=report['success'],execution_finished=report['execution_finished'],wb_write_attempts=report['wb_write_attempts'],telegram_calls=0,other_queue_calls=0,confirmed=sum(x.get('status')=='confirmed' for x in report['results']),stopped_changed=sum(x.get('status')=='stopped_changed_inputs_recalculated' for x in report['results']),not_executed=sum(not x.get('written') for x in report['results']),blocked_sku_lock_retained=report.get('blocked_sku_lock_retained'))
        if 'error' in report:public['error_type']=report['error']['type']
        (OUT/'controlled-summary.json').write_text(json.dumps(public));print(json.dumps(public))
    return 0 if report['success'] else 1
if __name__=='__main__':sys.exit(main())
