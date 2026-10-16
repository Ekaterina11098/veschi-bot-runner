import assert from 'node:assert/strict';
import {isReviewApprovalUpdate,routeReviewApproval} from './review_callback_route.mjs';
const msg=text=>({message:{from:{id:1},chat:{id:2,type:'private'},reply_to_message:{from:{id:3},text}}});
for(const type of ['Отзывы','Вопросы'])for(const cabinet of ['', 'Кабинет: ООО\n','Кабинет: ИП\n','Кабинет: Китай\n']){
 const u=msg(cabinet+'['+type+':согласование]\nsku');
 assert.equal(isReviewApprovalUpdate(u),true);
 const denied=await routeReviewApproval(new Request('https://example.org'),u,{enabled:false},()=>{throw Error('must not dispatch');});
 assert.equal(denied.status,200);
}
for(const text of ['обычное поручение','Пример [Вопросы:согласование]','Кабинет: чужой\n[Отзывы:согласование]'])assert.equal(isReviewApprovalUpdate(msg(text)),false);
assert.equal(isReviewApprovalUpdate({callback_query:{data:'rv1:token:v1'}}),true);
assert.equal(isReviewApprovalUpdate({callback_query:{data:'agent:ask'}}),false);
console.log('Question/review routing: 8 header forms, unrelated messages, callbacks and disabled isolation passed');
const cfg={enabled:true,mode:'github-encrypted',webhookSecret:'test-secret',receiverURL:'https://api.github.com/repos/Ekaterina11098/veschi-bot-runner/actions/workflows/review-approval-process.yml/dispatches',ingressKey:Buffer.alloc(32,7).toString('base64'),dispatchToken:'test-token',ownerId:'1',chatId:'2',botId:'3'};
const request=new Request('https://example.org',{headers:{'X-Telegram-Bot-Api-Secret-Token':'test-secret'}});
const update=msg('Кабинет: ООО\n[Вопросы:согласование]\nquestion');
let calls=0;
const response=await routeReviewApproval(request,update,cfg,async (url,options)=>{
 calls++;const envelope=JSON.parse(JSON.parse(options.body).inputs.sealed_update);
 const key=await crypto.subtle.importKey('raw',Buffer.alloc(32,7),'AES-GCM',false,['decrypt']);
 const actual=await crypto.subtle.decrypt({name:'AES-GCM',iv:Buffer.from(envelope.nonce,'base64'),additionalData:new TextEncoder().encode('review-approval-update-v1')},key,Buffer.from(envelope.ciphertext,'base64'));
 assert.deepEqual(JSON.parse(new TextDecoder().decode(actual)),update);
 return new Response(null,{status:204});
});
assert.equal(response.status,200);assert.equal(calls,1);
const forged=msg('Кабинет: ООО\n[Вопросы:согласование]\nquestion');forged.message.from.id=99;
await routeReviewApproval(request,forged,cfg,()=>{throw Error('Unauthorized forward');});
console.log('Encrypted exact update forwarding and owner authorization passed');

