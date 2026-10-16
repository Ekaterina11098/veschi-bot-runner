"""Remove only the bound, durably approved review card; never delete journal data."""
def dismiss_approved(approval, telegram, token, preserve=None):
    repo=approval.repo
    with repo.transaction():
        card=repo.get('cards',token,lock=True)
        if not card or card['status'] not in ('approved','sent','manual_present','uncertain','held'):
            raise ValueError('Only a durably approved publication card can be dismissed')
        # A local hold without publication approval is not an approved card.
        from review_telegram_approval import sha
        if card.get('selected') not in (0,1):raise ValueError('Approved selection required')
        intent=repo.get('intents',sha([card['ref'],card['version'],card['hashes'][card['selected']]]))
        if not intent or intent.get('card_token')!=token:raise ValueError('Exact approved intent required')
        if intent['owner_id']!=approval.owner or intent['chat_id']!=approval.chat:
            raise ValueError('Wrong approval owner/chat')
        old=card.get('telegram_card_removal')
        if old:return old
        removal={'status':'sending','message_id':card['message_id'],'intent_id':intent['id'],'created_at':approval.clock()}
        card['telegram_card_removal']=removal;repo.put('cards',token,card)
    # Text, exact approval and deletion intent are committed before Telegram.
    if preserve:preserve()
    try:
        response=telegram.call('deleteMessage',{'chat_id':approval.chat,'message_id':card['message_id']})
        if response is not True and not (isinstance(response,dict) and response.get('ok') is True):
            raise RuntimeError('Deletion not confirmed')
        status='confirmed'
    except Exception:status='uncertain'
    with repo.transaction():
        current=repo.get('cards',token,lock=True)
        current['telegram_card_removal'].update(status=status,checked_at=approval.clock())
        repo.put('cards',token,current)
    if preserve:preserve()
    return repo.get('cards',token)['telegram_card_removal']

def notify_owner_problem(approval,telegram,intent,preserve=None):
    """Only a blocked action needing owner review; routine pauses never notify."""
    if intent.get('status')!='blocked':return None
    if intent['owner_id']!=approval.owner or intent['chat_id']!=approval.chat:
        raise ValueError('Wrong problem recipient')
    key='owner-problem:'+intent['id']
    with approval.repo.transaction():
        approval.repo.get('intents',intent['id'],lock=True)
        old=approval.repo.get('events',key)
        if old:return old
        event={'status':'sending','intent_id':intent['id'],'created_at':approval.clock(),'needs_owner_decision':True}
        approval.repo.put('events',key,event)
    if preserve:preserve()
    card=approval.repo.get('cards',intent['card_token'])
    cabinet={'token_1':'ООО','token_2':'ИП','token_3':'Китай'}[intent['cabinet']]
    text='Отзывы · '+cabinet+' · '+str(card['source']['article'])[:150]+'\nНужно ваше решение: публикация остановлена, поскольку данные, версия ответа или блокировка изменились. Ответ не подтверждён WB. Проверьте актуальный отзыв перед новым согласованием.'
    try:
        response=telegram.call('notifyOwnerReviewProblem',{'chat_id':approval.chat,'text':text})
        mid=response.get('message_id') if isinstance(response,dict) else None
        if not isinstance(mid,int) or mid<=0:raise ValueError('Message id unconfirmed')
        event.update(status='confirmed',message_id=mid)
    except Exception:event['status']='uncertain'
    with approval.repo.transaction():approval.repo.put('events',key,event)
    if preserve:preserve()
    return event

def notify_owner_receipt(approval,telegram,intent,preserve=None):
    """One durable receipt per lifecycle stage; no automatic resend on timeout."""
    if intent['owner_id']!=approval.owner or intent['chat_id']!=approval.chat:
        raise ValueError('Wrong receipt recipient')
    stage=('public' if intent.get('wb_ui_status')=='Опубликован для всех' else
           {'confirmed':'accepted','verify':'verifying','manual_present':'manual_present','blocked':'blocked'}.get(intent.get('status'),'approved'))
    key='owner-receipt:'+intent['id']+':'+stage
    repo=approval.repo
    with repo.transaction():
        repo.get('intents',intent['id'],lock=True)
        old=repo.get('events',key)
        if old:return old
        event={'status':'sending','intent_id':intent['id'],'stage':stage,'created_at':approval.clock()}
        repo.put('events',key,event)
    if preserve:preserve()
    card=repo.get('cards',intent['card_token'])
    cabinet={'token_1':'ООО','token_2':'ИП','token_3':'Китай'}[intent['cabinet']]
    kind='Вопрос' if intent['kind']=='questions' else 'Отзыв'
    state={'public':'Ответ опубликован для всех в WB. Текст точно совпадает с подтверждённым.',
           'accepted':'WB подтвердил приём ответа. Текст совпадает; публичная публикация может проходить модерацию.',
           'approved':'Подтверждение принято и сохранено. Ответ ожидает отправки и проверки WB; повторно нажимать не нужно.',
           'verifying':'Ответ отправлялся, но подтверждение WB ещё не получено. Автоматически проверяем результат; повторная отправка заблокирована.',
           'manual_present':'В WB уже есть другой ответ. Повторная публикация остановлена, чтобы исключить дубли. Проверьте существующий ответ.',
           'blocked':'Публикация остановлена: изменились исходные данные, версия ответа или блокировка. Требуется ваша проверка; повторно отправлять прежний текст нельзя.'}[stage]
    text=kind+' · '+cabinet+' · '+str(card['source']['article'])[:150]+'\nID: '+intent['item_id']+'\n'+state
    try:
        response=telegram.call('notifyOwnerReviewReceipt',{'chat_id':approval.chat,'text':text})
        if not isinstance(response,dict) or str(response.get('chat',{}).get('id'))!=approval.chat or not isinstance(response.get('message_id'),int):raise ValueError('Receipt unconfirmed')
        event.update(status='confirmed',message_id=response['message_id'])
    except Exception:event['status']='uncertain'
    with repo.transaction():repo.put('events',key,event)
    if preserve:preserve()
    return event
