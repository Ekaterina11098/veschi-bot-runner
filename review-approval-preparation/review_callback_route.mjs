// Isolated optional branch for the EXISTING webhook, before legacy message parsing.
// null means unrelated update. No queue insertion, stock dispatch, WB or sendMessage.
export async function routeReviewApproval(request, update, config, forward = fetch) {
  const q = update?.callback_query;
  const message = q?.message ?? update?.message;
  const isReview = typeof q?.data === 'string' && q.data.startsWith('rv1:') ||
    typeof update?.message?.reply_to_message?.text === 'string' &&
    update.message.reply_to_message.text.startsWith('[Отзывы:согласование]\n');
  if (!isReview) return null;
  // Consume our callbacks while disabled: they must NEVER fall through to old queues.
  if (config.enabled !== true) return new Response('Review approval disabled', {status: 200});
  if (!config.webhookSecret || !config.receiverSecret || !config.receiverURL || !config.ownerId || !config.chatId || !config.botId)
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
    const result = await forward(config.receiverURL, {
      method: 'POST', headers: {'Content-Type': 'application/json', 'X-Telegram-Bot-Api-Secret-Token': config.receiverSecret},
      body: JSON.stringify(update), signal: AbortSignal.timeout(8000), redirect: 'error',
    });
    return new Response(result.ok ? 'OK' : 'Review receiver unavailable', {status: result.ok ? 200 : 503});
  } catch {
    return new Response('Review receiver unavailable', {status: 503});
  }
}
