import test from 'node:test';
import assert from 'node:assert/strict';
import { recentContext, contextBeforeReply } from './context.js';
import { initialState, message, serialize, restore } from './state.js';

test('full normal text history, including closing, with bounded text', () => {
  const messages = Array.from({length:5}, (_, i) => [
    {role:'user', text:`topic ${i}`, products:[{secret:'not sent'}], attachments:[{image:'not sent'}]},
    {role:'assistant', text:`answer ${i}`, closing_text:`closing ${i}`, products:[{product_id:'not sent'}]},
  ]).flat();
  const context = recentContext(messages);
  assert.equal(context.length, 10);
  assert.deepEqual(context[0], {role:'user',text:'topic 0'});
  assert.deepEqual(context[9], {role:'assistant',text:'answer 4\nclosing 4'});
  assert.ok(!JSON.stringify(context).includes('not sent'));
  assert.equal(recentContext([{role:'user',text:'a'.repeat(2000)}])[0].text.length,2000);
});
test('old history uses available text and strips image paths and metadata', () => {
  const state = initialState();
  state.conversations[0].messages = [message('user','white tees'), message('assistant',
    'White is versatile. ![photo](data/images/tshirt/1.jpg)\nproduct_id: 123\n/images/tshirt/1.jpg https://example.com/image.jpg')];
  const context = recentContext(restore(serialize(state)).conversations[0].messages);
  assert.deepEqual(context, [{role:'user',text:'white tees'}, {role:'assistant',text:'White is versatile.'}]);
});
test('retry context excludes its current turn, later turns, pending/errors and other chats', () => {
  const messages = [{id:'u1',role:'user',text:'Japanese tees'}, {id:'a1',role:'assistant',text:'Relaxed silhouettes.'},
    {id:'u2',role:'user',text:'darker'}, {id:'a2',role:'assistant',text:'',status:'pending'},
    {id:'u3',role:'user',text:'later query'}, {id:'a3',role:'assistant',text:'later answer'}];
  assert.deepEqual(contextBeforeReply(messages,'a2'), [{role:'user',text:'Japanese tees'}, {role:'assistant',text:'Relaxed silhouettes.'}]);
  assert.deepEqual(contextBeforeReply(messages,'a1'), []);
  assert.deepEqual(recentContext(messages.slice(2,4)), []);
  assert.deepEqual(recentContext([]), []);
  assert.deepEqual(contextBeforeReply(messages,'unknown'), []);
});
