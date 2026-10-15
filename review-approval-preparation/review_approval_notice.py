"""Explicit new-review notification only. No enumeration or replay of old notices."""
from review_telegram_approval import sha,identity,Rejected
from review_telegram_runtime import TelegramTransport

class NewNoticeTransport(TelegramTransport):
    ALLOWED=frozenset(('sendMessage','getMe','getChat','editMessageText'))

class NewNotice:
    def __init__(self,approval,bridge,telegram,enabled=False):
        self.a=approval;self.bridge=bridge;self.tg=telegram;self.enabled=enabled
    def deliver(self,item,cabinet,kind,version,observed_at,cutover):
        if not self.enabled:raise Rejected('New review notices disabled')
        if observed_at<cutover:raise Rejected('Old observation before cutover')
        source=self.bridge.source
        if source.was_notified(cabinet,kind,str(item['id'])):raise Rejected('Existing notice: do not replay')
        key=self.bridge.draft_key(cabinet,kind,item['id'],version);draft=source.read(key)
        if not draft or draft.get('source_sha256')!=sha(item):raise Rejected('Exact durable draft required')
        context=dict(buyer=item.get('userName',''),rating=item.get('productValuation',0),text=item.get('text',''),pros=item.get('pros',''),cons=item.get('cons',''),article=(item.get('productDetails') or {}).get('supplierArticle',''))
        ref=identity(cabinet,kind,item['id'])
        card=dict(ref=ref,cabinet=cabinet,kind=kind,item_id=str(item['id']),version=version,source=context,texts=draft['variants'],hashes=[sha(t) for t in draft['variants']],binding={'draft_key':key,'raw_source_sha256':sha(item)},message_id=1,status='awaiting')
        state=self.bridge.project(card)
        if not state.get('complete') or state['hold'] or state['answered'] or state['publication_state']!='idle':raise Rejected('Review blocked')
        bot=self.tg.call('getMe',{});chat=self.tg.call('getChat',{'chat_id':self.a.chat})
        if str(bot.get('id'))!=self.a.bot or str(chat.get('id'))!=self.a.chat or chat.get('type')!='private':raise Rejected('Verified destination mismatch')
        notice_key='new-notice:'+sha([ref,version])
        with self.a.repo.transaction():
            if self.a.repo.pg:self.a.repo.execute('SELECT pg_advisory_xact_lock(hashtextextended(?,0))',(notice_key,))
            if self.a.repo.get('events',notice_key):return {'status':'blocked_existing_delivery','automatic_retry':False}
            self.a.repo.put('events',notice_key,{'status':'sending','ref':ref,'version':version,'observed_at':observed_at,'cutover':cutover})
        if self.a.repo.get('events',notice_key)['status']!='sending':raise RuntimeError('Notice claim readback')
        try:
            text=self.a.view('unbound',card)['text']
            if len(text.encode('utf-16-le'))//2>4096:raise ValueError('Card too long')
            message=self.tg.call('sendMessage',{'chat_id':self.a.chat,'text':text})
            if str(message.get('chat',{}).get('id'))!=self.a.chat or str(message.get('from',{}).get('id'))!=self.a.bot:raise ValueError('Message identity mismatch')
            message_id=message['message_id']
        except Exception:
            with self.a.repo.transaction():self.a.repo.put('events',notice_key,{'status':'uncertain','ref':ref,'version':version,'automatic_retry':False})
            return {'status':'uncertain','automatic_retry':False}
        # Save confirmed delivery BEFORE attaching buttons. Never resend if binding fails.
        with self.a.repo.transaction():self.a.repo.put('events',notice_key,{'status':'confirmed','ref':ref,'version':version,'message_id':message_id})
        token,view=self.bridge.create(item,cabinet,kind,version,message_id)
        try:
            self.tg.call('editMessageText',{'chat_id':self.a.chat,'message_id':message_id,'text':view['text'],'reply_markup':view['reply_markup']})
            attachment='confirmed'
        except Exception:attachment='uncertain'
        return {'status':'confirmed','message_id':message_id,'card_token':token,'buttons':attachment,'automatic_retry':False}

