export function isReviewApprovalUpdate(update) {
  if (typeof update?.callback_query?.data === 'string' && update.callback_query.data.startsWith('rv1:')) return true;
  const text = update?.message?.reply_to_message?.text;
  return typeof text === 'string' && /^(?:Кабинет: (?:ООО|ИП|Китай)\n)?\[(?:Отзывы|Вопросы):согласование\](?:\n|$)/u.test(text);
}
// Isolated optional branch for the EXISTING webhook, before legacy message parsing.
// null means unrelated update. No queue insertion, stock dispatch, WB or sendMessage.
export async function routeReviewApproval(request, update, config, forward = fetch) {
  const q = update?.callback_query;
  const message = q?.message ?? update?.message;
  const isReview = isReviewApprovalUpdate(update);
  if (!isReview) return null;
  // Consume our callbacks while disabled: they must NEVER fall through to old queues.
  if (config.enabled !== true) return new Response('Review approval disabled', {status: 200});
  if (!config.webhookSecret || !config.receiverURL || !config.ownerId || !config.chatId || !config.botId ||
      (config.mode === 'github-encrypted' ? (!config.ingressKey || !config.dispatchToken) : !config.receiverSecret))
    return new Response('Review configuration incomplete', {status: 503});
  if (request.headers.get('X-Telegram-Bot-Api-Secret-Token') !== config.webhookSecret)
    return new Response('Unauthorized', {status: 401});
  const actor = q?.from ?? update.message?.from;
  if (String(actor?.id) !== String(config.ownerId) || String(message?.chat?.id) !== String(config.chatId) || message?.chat?.type !== 'private')
    return new Response('OK', {status: 200});
  const origin = q ? message : update.message.reply_to_message;
  if (String(origin?.from?.id) !== String(config.botId) || origin?.forward_origin)
    return new Response('OK', {status: 200});
  if (!config.receiverURL.startsWith('https://')) return new Response('Invalid receiver', {status: 503});
  try {
    if (config.mode === 'github-encrypted') {
      const expected='https://api.github.com/repos/Ekaterina11098/veschi-bot-runner/actions/workflows/review-approval-process.yml/dispatches';
      if (config.receiverURL !== expected) return new Response('Invalid dispatch target', {status:503});
      const bytes=Uint8Array.from(atob(config.ingressKey),c=>c.charCodeAt(0));
      if(bytes.length!==32)return new Response('Invalid ingress key', {status:503});
      const key=await crypto.subtle.importKey('raw',bytes,'AES-GCM',false,['encrypt']);
      const nonce=crypto.getRandomValues(new Uint8Array(12));
      const ciphertext=await crypto.subtle.encrypt({name:'AES-GCM',iv:nonce,additionalData:new TextEncoder().encode('review-approval-update-v1')},key,new TextEncoder().encode(JSON.stringify(update)));
      const b64=value=>btoa(String.fromCharCode(...new Uint8Array(value)));
      const sealed=JSON.stringify({format:'review-approval-update-v1',nonce:b64(nonce),ciphertext:b64(ciphertext)});
      const result=await forward(expected,{method:'POST',headers:{'Authorization':'Bearer '+config.dispatchToken,'Accept':'application/vnd.github+json','Content-Type':'application/json'},body:JSON.stringify({ref:'main',inputs:{sealed_update:sealed}}),signal:AbortSignal.timeout(8000),redirect:'error'});
      if(result.ok && q?.id)return Response.json({method:'answerCallbackQuery',callback_query_id:q.id,text:'Проверяю согласование…'});
      return new Response(result.ok?'OK':'Review dispatch unavailable',{status:result.ok?200:503});
    }
    const result = await forward(config.receiverURL, {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Telegram-Bot-Api-Secret-Token': config.receiverSecret},
      body: JSON.stringify(update), signal: AbortSignal.timeout(8000), redirect: 'error',
    });
    return new Response(result.ok ? 'OK' : 'Review receiver unavailable', {status: result.ok ? 200 : 503});
  } catch {
    return new Response('Review receiver unavailable', {status: 503});
  }
}

