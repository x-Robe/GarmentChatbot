import test from 'node:test';
import assert from 'node:assert/strict';
import { initialState, createConversation, message, restore, serialize, titleFor, validateFile, MAX_FILE_SIZE } from './state.js';

test('history round trip preserves messages, product labels, attachments and active chat', () => {
  const state = initialState();
  const original = state.conversations[0];
  original.messages.push(message('user', 'black tee', { attachments: [{ id: 'file-1', name: 'shirt.png', type: 'image/png', size: 123, previewUrl: 'blob:temporary' }] }));
  original.messages.push(message('assistant', 'One match', { products: [{ id: '1', title: 'Tee', image: '/1.png', attributes: { Colour: 'Black' }, match_type: 'exact' }] }));
  const next = createConversation();
  state.conversations.push(next); state.activeId = next.id; state.mode = 'similar';
  const raw = serialize(state);
  assert.ok(!raw.includes('blob:temporary'));
  const loaded = restore(raw);
  assert.equal(loaded.conversations.length, 2);
  assert.equal(loaded.activeId, next.id);
  assert.equal(loaded.mode, 'similar');
  assert.equal(loaded.conversations[0].messages[0].attachments[0].name, 'shirt.png');
  assert.equal(loaded.conversations[0].messages[1].products[0].match_type, 'exact');
});
test('refresh converts pending replies to retryable interrupted searches', () => {
  const state = initialState();
  state.conversations[0].messages.push(message('assistant', '', {status:'pending', request:{query:'black', mode:'exact'}}));
  const entry = restore(serialize(state)).conversations[0].messages[0];
  assert.equal(entry.status, 'interrupted');
  assert.equal(entry.request.mode, 'exact');
});
test('invalid saved data is rejected without silently discarding history', () => {
  assert.throws(() => restore('{bad'));
  assert.throws(() => restore('{"version":2}'));
  const state = initialState(); state.conversations[0].messages.push({ role:'user', text:2 });
  assert.throws(() => restore(serialize(state)));
});
test('titles use first text or attachment fallback, within 40 characters', () => {
  assert.equal(titleFor('  black   oversized tee '), 'Black oversized tee');
  assert.equal(titleFor('', [{type:'image/png'}]), 'Image reference');
  assert.equal(titleFor('', [{type:'application/pdf'}]), 'Uploaded reference');
  assert.ok(titleFor('long '.repeat(30)).length <= 40);
});
test('file validation accepts supported types and rejects oversized/empty/mismatched files', () => {
  assert.equal(validateFile({ name:'PHOTO.JPG', type:'image/jpeg', size:100 }).type, 'image/jpeg');
  assert.ok(validateFile({ name:'reference.pdf', type:'', size:100 }).error);
  for (const file of [
    {name:'app.exe',type:'',size:100},
    {name:'image.png',type:'image/png',size:MAX_FILE_SIZE+1},
    {name:'image.png',type:'image/png',size:0},
    {name:'image.png',type:'text/html',size:100},
  ]) assert.ok(validateFile(file).error);
});

test('real API product snapshots and response ID survive refresh', () => {
  const state = initialState();
  const products = [{ product_id: '123', point_id: 'point', image_url: '/images/tshirt/1.jpg', image_path: 'data/images/tshirt/1.jpg', image: 'http://127.0.0.1:8001/images/tshirt/1.jpg', title: 'black · oversized', attributes: { colors: ['black'], style: ['oversized'] }, match_type: 'exact', similarity_score: 0.91 }];
  const reply = message('assistant', 'Backend text', { response_id: 'resp_real', products, search_results: { exact: products, similar: [] } });
  state.conversations[0].messages.push(reply);
  assert.deepEqual(restore(serialize(state)).conversations[0].messages[0], reply);
});


test('legacy Default history migrates without losing products, closing or route', () => {
  const state = initialState(); state.mode = 'default';
  const entry = message('assistant', 'One reference', { request: { query: 'tee', mode: 'default' },
    closing_text: 'Try a darker direction.', search_strategy: 'similar', intent: 'search', products: [] });
  state.conversations[0].messages.push(entry);
  const restored = restore(serialize(state));
  assert.equal(restored.mode, 'auto');
  const reply = restored.conversations[0].messages[0];
  assert.equal(reply.request.mode, 'auto');
  assert.equal(reply.closing_text, entry.closing_text);
  assert.equal(reply.search_strategy, 'similar');
  assert.equal(restored.conversations[0].id, state.conversations[0].id);
});
