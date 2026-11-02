export const THREAD='01a14b40-d7b4-76b1-a8eb-9bc1eea36335';
export function route(text,policy,message,now=Date.now()) {
 if(!policy?.enabled)return {kind:'legacy',text};
 if(policy.thread_id!==THREAD||policy.chat_id!==-1004342917488||policy.bot_id!==8780468043)throw Error('Bridge scope mismatch');
 if(message.chat.id!==policy.chat_id||!policy.allowed_sender_ids.includes(message.from.id))return {kind:'legacy',text};
 const legacy=/^(?:Агент\s*[,,:]\s*|\/agent(?:@[A-Za-z0-9_]+)?\s+)([\s\S]+)$/iu.exec(text);
 if(legacy)return {kind:'legacy_explicit',text:legacy[1].trim()};
 if(!Number.isFinite(Date.parse(policy.expires_at))||now>=Date.parse(policy.expires_at))return {kind:'expired',text};
 const addressed=/^(?:Кодекс\s*[,,:]\s*|\/codex(?:@[A-Za-z0-9_]+)?\s+)([\s\S]+)$/iu.exec(text);
 return {kind:'codex',text:addressed?addressed[1].trim():text};
}
