"""Read-only bridge to the existing durable review cache. No old queue writes."""
import json
from review_telegram_approval import sha, Rejected

def reply_key(cabinet,kind,item_id):
    return str(item_id) if cabinet=='token_1' and kind=='feedbacks' else 'veschi-review:'+cabinet+':'+kind+':'+str(item_id)

class SQLSource:
    def __init__(self,connection): self.conn=connection
    def read(self,key):
        row=self.conn.execute('SELECT payload FROM review_approval.source_cache WHERE cache_key=%s',(key,)).fetchone()
        return row[0] if row else None
    def matching(self,cabinet,kind,item_id,prefix):
        if prefix=='reviews:publication:':
            return [row[0] for row in self.conn.execute("SELECT payload FROM review_approval.source_cache WHERE starts_with(cache_key,%s)",(prefix+cabinet+':'+str(item_id)+':',)).fetchall()]
        return [row[0] for row in self.conn.execute("SELECT payload FROM review_approval.source_cache WHERE starts_with(cache_key,%s) AND payload->>'cabinet'=%s AND coalesce(payload->>'kind','feedbacks')=%s AND payload->>'item_id'=%s ORDER BY updated_at DESC,cache_key",(prefix,cabinet,kind,str(item_id))).fetchall()]
    def journal(self,key):
        row=self.conn.execute('SELECT state,error FROM review_approval.source_journal WHERE feedback_id=%s',(key,)).fetchone()
        return dict(state=row[0],error=row[1]) if row else None
    def was_notified(self,cabinet,kind,item_id):
        suffix=cabinet+':'+str(item_id)
        return self.conn.execute("SELECT EXISTS(SELECT 1 FROM review_approval.source_cache WHERE starts_with(cache_key,'reviews:notice:') AND right(coalesce(payload->>'scope',''),%s)=%s)",(len(suffix),suffix)).fetchone()[0]

class DurableBridge:
    def __init__(self,approval,source):self.approval=approval;self.source=source
    def draft_key(self,cabinet,kind,item_id,version):return 'reviews:draft:'+sha([reply_key(cabinet,kind,item_id),version])
    def create(self,item,cabinet,kind,version,message_id):
        key=self.draft_key(cabinet,kind,item['id'],version);draft=self.source.read(key)
        if not draft or draft.get('source_sha256')!=sha(item):raise Rejected('Saved source/draft mismatch')
        context=dict(buyer=item.get('userName',''),rating=item.get('productValuation',0),text=item.get('text',''),pros=item.get('pros',''),cons=item.get('cons',''),article=(item.get('productDetails') or {}).get('supplierArticle',''))
        projection=dict(cabinet=cabinet,kind=kind,item_id=str(item['id']),version=version,source=context,
            hashes=[sha(t) for t in draft['variants']],binding={'draft_key':key,'raw_source_sha256':sha(item)})
        if not self.project(projection).get('complete'):raise Rejected('Canonical draft unavailable')
        state=self.project(projection)
        if state['hold'] or state['answered'] or state['publication_state']!='idle':raise Rejected('Canonical review blocked')
        return self.approval.create(cabinet,kind,item['id'],version,context,draft['variants'],message_id,binding=projection['binding'],order_status=item.get('orderStatus'))
    def project(self,card):
        cabinet,kind,item_id=card['cabinet'],card['kind'],card['item_id']
        binding=card.get('binding') or {};key=self.draft_key(cabinet,kind,item_id,card['version'])
        if binding.get('draft_key')!=key:return {'complete':False}
        draft=self.source.read(key)
        if not draft or draft.get('source_sha256')!=binding.get('raw_source_sha256'):return {'complete':False}
        if draft.get('confirmation_status') not in ('draft','owner_hold'):return {'complete':False}
        versions=self.source.matching(cabinet,kind,item_id,'reviews:draft:')
        if not versions or versions[0].get('version')!=card['version']:return {'complete':False}
        hold=self.source.read('reviews:hold:'+cabinet+':'+kind+':'+item_id)
        journal=self.source.journal(reply_key(cabinet,kind,item_id))
        phase='idle';answered=False
        if journal:
            answered=journal['state']=='sent'
            if not answered:phase='uncertain'  # Never adopt old pending/needs_check jobs.
        for publication in self.source.matching(cabinet,kind,item_id,'reviews:publication:'):
            if publication.get('phase') in ('confirmed','manual_present'):answered=True
            else:phase='uncertain'
        return dict(complete=True,ref=card.get('ref'),hold=bool((hold or {}).get('active')) or draft.get('confirmation_status')=='owner_hold',answered=answered,publication_state=phase,version=draft['version'],hashes=[sha(t) for t in draft['variants']],source_sha256=sha(card['source']))


