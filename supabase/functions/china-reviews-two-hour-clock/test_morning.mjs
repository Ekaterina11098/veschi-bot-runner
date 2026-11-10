import assert from 'node:assert/strict';
import {morningDecision as decide} from './morning.mjs';
const now=new Date('2026-11-11T05:00:00Z');
assert.equal(decide(new Date('2026-11-11T04:59:00Z'),{},[],[]).status,'outside_window');
assert.equal(decide(now,{},[],[]).status,'dispatch');
for(const status of ['queued','in_progress','pending','waiting','requested'])
 assert.equal(decide(now,{},[{status}],[]).status,'active');
for(const status of ['submitting','uncertain'])
 assert.equal(decide(now,{},[],[{status}]).status,'uncertain');
assert.equal(decide(now,{},[],[{status:'dispatched',created_at:now.toISOString()}]).status,'awaiting_run');
const observed={id:42,path:'.github/workflows/reviews-morning.yml',status:'completed',updated_at:'2026-11-11T04:50:00Z'};
assert.equal(decide(now,{},[observed],[{status:'observed_active',observed_run_id:42}]).status,'dispatch');
assert.equal(decide(now,{},[],[{status:'observed_active',observed_run_id:42}]).status,'awaiting_run');
const done={status:'complete',summary:{status:'confirmed'},scopes:Object.fromEntries(['token_1','token_2','token_3'].map(c=>[c,{status:'complete'}]))};
assert.equal(decide(now,{reviews:done,questions:done},[],[]).status,'complete');
assert.equal(decide(now,{reviews:done},[],[]).status,'dispatch');
assert.equal(decide(new Date('2026-11-11T09:50:00Z'),{},[],[]).status,'outside_window');
console.log('Morning clock policy: passed');

