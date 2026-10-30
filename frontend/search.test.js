import test from 'node:test';
import assert from 'node:assert/strict';
import { searchReferences, resolveImageUrl, productView } from './search.js';
import { API_BASE_URL } from './config.js';
const payload = () => ({ text: 'Real backend wording\nSecond line', response_id: 'r1', products: [
  { product_id: '1', image_url: '/images/tshirt/1.jpg', image_path: 'data/images/tshirt/1.jpg', attributes: { colors: ['black'], style: ['oversized'] }, match_type: 'exact' },
  { product_id: '2', image_url: null, attributes: {}, match_type: 'similar' },
], search_results: { exact: [], similar: [] } });

test('POST sends only query and selected mode; preserves backend text, order and metadata', async t => {
  for (const mode of ['auto', 'default', 'exact', 'similar']) {
    t.mock.method(globalThis, 'fetch', async (url, options) => {
      assert.equal(String(url), `${API_BASE_URL}/api/chat`);
      assert.equal(options.method, 'POST');
      assert.equal(options.headers['Content-Type'], 'application/json');
      assert.deepEqual(JSON.parse(options.body), { query: 'black tee', mode });
      return new Response(JSON.stringify(payload()));
    });
    const reply = await searchReferences({ query: 'black tee', mode, attachments: ['not sent'] });
    assert.equal(reply.text, payload().text);
    assert.equal(reply.response_id, 'r1');
    assert.deepEqual(reply.products.map(p => p.product_id), ['1', '2']);
    assert.equal(reply.products[0].image, `${API_BASE_URL}/images/tshirt/1.jpg`);
    assert.equal(reply.products[0].title, 'oversized · black');
    assert.equal(reply.products[1].image, '');
    assert.equal(reply.products[0].image_path, payload().products[0].image_path);
    t.mock.restoreAll();
  }
});
test('image URLs resolve against API origin and reject unsafe schemes', () => {
  assert.equal(resolveImageUrl('/images/tshirt/1.jpg'), `${API_BASE_URL}/images/tshirt/1.jpg`);
  assert.equal(resolveImageUrl('https://example.com/1.jpg'), 'https://example.com/1.jpg');
  for (const value of [null, undefined, '', 'javascript:alert(1)', 'file:///tmp/a']) assert.equal(resolveImageUrl(value), '');
});
test('empty products retain backend explanation', async t => {
  const data = { ...payload(), products: [], text: 'Nothing found by backend' };
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify(data)));
  assert.deepEqual(await searchReferences({ query: 'tee', mode: 'exact' }), data);
});
test('HTTP failures never display server error content', async t => {
  for (const status of [422, 502, 503]) {
    t.mock.method(globalThis, 'fetch', async () => new Response('internal detail', { status }));
    await assert.rejects(searchReferences({ query: 'tee', mode: 'default' }), /Please try again/);
    t.mock.restoreAll();
  }
});
test('network errors give a useful connection message', async t => {
  t.mock.method(globalThis, 'fetch', async () => { throw new TypeError('secret detail'); });
  await assert.rejects(searchReferences({ query: 'tee', mode: 'default' }), /Cannot connect to the Garment backend/);
});
test('malformed JSON and malformed response shapes fail cleanly', async t => {
  for (const body of ['{bad', '{}', JSON.stringify({ ...payload(), products: [null] }), JSON.stringify({ ...payload(), search_results: {} })]) {
    t.mock.method(globalThis, 'fetch', async () => new Response(body));
    await assert.rejects(searchReferences({ query: 'tee', mode: 'default' }), /Please try again/);
    t.mock.restoreAll();
  }
});
test('abort signal reaches fetch and cancellation stays an AbortError', async t => {
  const controller = new AbortController(); controller.abort();
  t.mock.method(globalThis, 'fetch', async (_, options) => {
    assert.equal(options.signal, controller.signal);
    throw new DOMException('Aborted', 'AbortError');
  });
  await assert.rejects(searchReferences({ query: 'tee', mode: 'exact', signal: controller.signal }), { name: 'AbortError' });
});

test('card metadata uses at most four real tags without changing product data', () => {
  const product = { attributes: { style: ['streetwear', 'sportswear'], patterns: ['graphic', 'printed'], neckline: 'mock neck', sleeve: 'short sleeve', colors: ['black'], category: 't-shirt' } };
  const before = structuredClone(product);
  const view = productView(product);
  assert.equal(view.title, 'streetwear · graphic · mock neck · short sleeve');
  assert.deepEqual(product, before);
  assert.deepEqual(view.attributes, before.attributes);
});


test('structured closing and intent pass through; only products become cards', async t => {
  const data = { ...payload(), closing_text: 'Try darker shades.', intent: 'search', search_strategy: 'both' };
  data.search_results.similar.push({ product_id: 'hidden', attributes: {} });
  t.mock.method(globalThis, 'fetch', async () => new Response(JSON.stringify(data)));
  const reply = await searchReferences({ query: 'tee', mode: 'auto' });
  assert.equal(reply.closing_text, data.closing_text);
  assert.equal(reply.search_strategy, 'both');
  assert.equal(reply.products.length, 2);
  assert.ok(!reply.products.some(p => p.product_id === 'hidden'));
});

test('optional context is sent with current query and mode; resolved query is preserved', async t => {
  const context = [{role:'user',text:'Japanese streetwear tees'}, {role:'assistant',text:'Try dark tones.'}];
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    assert.deepEqual(JSON.parse(options.body), {query:'make them darker',mode:'auto',context});
    return new Response(JSON.stringify({...payload(),resolved_query:'dark Japanese streetwear tees'}));
  });
  const reply = await searchReferences({query:'make them darker',mode:'auto',context});
  assert.equal(reply.resolved_query,'dark Japanese streetwear tees');
});
