import test from 'node:test';
import assert from 'node:assert/strict';
import { assistantDisplayText } from './presentation.js';
test('suppresses only internal image markdown and local image references', () => {
  assert.equal(assistantDisplayText('Matches:\n![Image](data/images/tshirt/1.jpg)\n![Image](/images/tshirt/2.jpg)'), 'Matches:');
  assert.equal(assistantDisplayText('See data/images/tshirt/1.jpg and /images/tshirt/2.png here.'), 'See  and  here.');
});
test('preserves normal summaries, external URLs, scores and product list text', () => {
  for (const text of ['I found 5 white T-shirts. Most have short sleeves.', '1. White T-shirt\n2. Black T-shirt', 'See https://example.com/images/1.jpg', 'No exact matches. Try Similar mode.', 'I’m GARMENT, a fashion inspiration assistant.']) {
    assert.equal(assistantDisplayText(text), text);
  }
});

import { userDisplayText } from './presentation.js';
import { recentContext } from './context.js';
import { readFileSync } from 'node:fs';
const attachment={id:'image1',name:'reference.jpg',type:'image/jpeg',size:100};
const request=query=>({type:'image',attachment_id:'image1',file_name:'reference.jpg',query});
const image=text=>({role:'user',search_type:'image',text,attachments:[attachment]});
test('new image text and image-only remain authored text, with separate unchanged attachments',()=>{
  for(const text of ['', 'get me some short-sleeves version', 'Image search: reference.jpg — my own words']) {
    const entry=image(text), before=JSON.stringify(entry);
    assert.equal(userDisplayText(entry,request(text)),text);
    assert.equal(JSON.stringify(entry),before);
  }
});
test('legacy labels require matching attachment and original request, without rewriting history',()=>{
  for(const query of ['', 'make it black']) {
    const entry=image(`Image search: reference.jpg${query ? ` — ${query}` : ''}`),before=JSON.stringify(entry);
    assert.equal(userDisplayText(entry,request(query)),query);
    assert.equal(JSON.stringify(entry),before);
    assert.equal(userDisplayText(entry,{...request(query),file_name:'other.jpg'}),entry.text);
    assert.equal(userDisplayText(entry),entry.text);
  }
});
test('ordinary text, filenames and uncorroborated image labels are preserved',()=>{
  for(const text of ['Image search: reference.jpg — make it black','Discuss Image search and reference.jpg']) {
    assert.equal(userDisplayText({role:'user',text},request('make it black')),text);
    assert.equal(userDisplayText(image(text),request('different query')),text);
  }
});
test('full history keeps image routing marker and authored query without technical filename label',()=>{
  for(const legacy of [false,true]) for(const query of ['', 'make it black']) {
    const entry=image(legacy ? `Image search: reference.jpg${query ? ` — ${query}` : ''}` : query);
    const context=recentContext([entry,{role:'assistant',text:'Results',request:request(query)}]);
    assert.equal(context[0].text,`Reference image search${query ? `: ${query}` : ''}`);
    assert.ok(!JSON.stringify(context).includes('reference.jpg'));
  }
});
test('attachment UI exposes only accessible supported image input, with no dangling PDF handler',()=>{
  const html=readFileSync(new URL('./index.html',import.meta.url),'utf8');
  const app=readFileSync(new URL('./app.js',import.meta.url),'utf8');
  assert.match(html, /id="choose-image">Add image/);
  assert.match(html,/aria-controls="attachment-menu"/);
  assert.match(html,/accept=".jpg,.jpeg,.png,.webp"/);
  assert.match(html,/10 MiB/);
  assert.doesNotMatch(html,/Add PDF|PDF search|choose-file|\.pdf/);
  assert.doesNotMatch(app,/choose-file/);
});
