import {test} from 'node:test';
import assert from 'node:assert/strict';
import {routeReviewApproval} from './review_callback_route.mjs';
const cfg={enabled:true,webhookSecret:'webhook',receiverSecret:'receiver',receiverURL:'https://review.invalid',ownerId:'11',chatId:'22',botId:'33'};
const request=()=>new Request('https://webhook.invalid',{method:'POST',headers:{'X-Telegram-Bot-Api-Secret-Token':'webhook'}});
const update=()=>({callback_query:{id:'1',data:'rv1:token:v1',from:{id:11},message:{message_id:101,from:{id:33},chat:{id:22,type:'private'}}}});
test('disabled never forwards',async()=>assert.equal((await routeReviewApproval(request(),update(),{...cfg,enabled:false},()=>assert.fail())).status,200));
test('stock command falls through without forwarding',async()=>assert.equal(await routeReviewApproval(request(),{message:{text:'остатки'}},cfg,()=>assert.fail()),null));
test('old callback falls through',async()=>assert.equal(await routeReviewApproval(request(),{callback_query:{data:'old:1'}},cfg,()=>assert.fail()),null));
test('wrong secret rejected',async()=>assert.equal((await routeReviewApproval(new Request('https://test.invalid'),update(),cfg,()=>assert.fail())).status,401));
test('wrong owner never forwards',async()=>{let u=update();u.callback_query.from.id=99;assert.equal((await routeReviewApproval(request(),u,cfg,()=>assert.fail())).status,200)});
test('wrong chat never forwards',async()=>{let u=update();u.callback_query.message.chat.id=99;assert.equal((await routeReviewApproval(request(),u,cfg,()=>assert.fail())).status,200)});
test('forward only dedicated receiver',async()=>{
 let calls=[];const result=await routeReviewApproval(request(),update(),cfg,async(url,payload)=>{calls.push([url,payload]);return new Response('OK')});
 assert.equal(result.status,200);assert.equal(calls.length,1);assert.equal(calls[0][0],cfg.receiverURL);
 assert.equal(calls[0][1].headers['X-Telegram-Bot-Api-Secret-Token'],'receiver');
 assert.deepEqual(JSON.parse(calls[0][1].body),update());
});
test('receiver failure returned without dispatch or retry',async()=>{let n=0;const r=await routeReviewApproval(request(),update(),cfg,async()=>{n++;throw Error('secret')});assert.equal(r.status,503);assert.equal(n,1)});
test('owner rework reply uses same isolated route',async()=>{
 const u={message:{from:{id:11},chat:{id:22,type:'private'},text:'Сократить',reply_to_message:{from:{id:33},text:'[Отзывы:согласование]\nООО'}}};
 assert.equal((await routeReviewApproval(request(),u,cfg,async()=>new Response('OK'))).status,200);
});
