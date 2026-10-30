import test from 'node:test';
import assert from 'node:assert/strict';
import { carouselState, pageProducts, detailRows, matchLabel } from './products.js';
import { initialState, message, serialize, restore } from './state.js';
const products = Array.from({length:8}, (_, i) => ({product_id:String(i+1), title:'Reference', image:'', attributes:{colors:['gray','blue'], style:['oversized'], patterns:[], neckline:'mock neck', sleeve:'short sleeve', buttons:false}, match_type:i<4?'exact':'similar'}));
test('1 and 4 products need only one page', () => {
  for (const count of [1,4]) {
    const state = carouselState(count);
    assert.equal(state.pages,1);
    assert.equal(pageProducts(products.slice(0,count),state.page).length,count);
    state.move(1); assert.equal(state.page,0);
  }
});
test('8 products navigate four at a time without reordering or mutation', () => {
  const original = structuredClone(products), state = carouselState(8);
  assert.deepEqual(pageProducts(products,state.page).map(p=>p.product_id),['1','2','3','4']);
  state.select(1); assert.equal(state.selected,1);
  state.move(1); assert.equal(state.selected,null);
  assert.deepEqual(pageProducts(products,state.page).map(p=>p.product_id),['5','6','7','8']);
  state.move(1); assert.equal(state.page,1);
  state.select(5); assert.equal(state.selected,5);
  state.select(0); assert.equal(state.selected,5);
  state.move(-1); assert.equal(state.page,0);
  assert.deepEqual(products,original);
});
test('details contain real meaningful attributes and correct match only', () => {
  assert.deepEqual(detailRows(products[0]), [['Color','Gray · Blue'],['Style','Oversized'],['Neckline','Mock neck'],['Sleeve','Short sleeve'],['Buttons','No'],['Match','Exact']]);
  assert.equal(matchLabel(products[7]),'Similar');
  assert.equal(detailRows(products[7]).at(-1)[1],'Similar');
  assert.ok(!detailRows(products[0]).some(([label])=>label==='Material'));
});
test('empty and missing fields are omitted without invented material', () => {
  assert.deepEqual(detailRows({attributes:{colors:[],style:null,patterns:[''],neckline:undefined},point_id:'hidden',image_path:'hidden'}),[]);
  assert.deepEqual(detailRows({attributes:{material:'cotton',buttons:true}}),[['Buttons','Yes'],['Material','Cotton']]);
});
test('restored history retains all products; new UI starts unselected on page 1', () => {
  const history=initialState(); history.conversations[0].messages.push(message('assistant','Real reply',{products}));
  const saved=restore(serialize(history)).conversations[0].messages[0].products;
  assert.deepEqual(saved,products);
  const state=carouselState(saved.length);
  assert.equal(state.page,0);assert.equal(state.selected,null);
  state.move(1);state.select(4);
  assert.equal(detailRows(saved[state.selected]).at(-1)[1],'Similar');
});

test('every supported count has real cards, bounded navigation, details and history', () => {
  for (const count of [1,2,3,4,5,7,8]) {
    const items=products.slice(0,count), ui=carouselState(count), seen=[];
    for(let page=0;page<Math.ceil(count/4);page++) {
      const cards=pageProducts(items,ui.page);
      assert.equal(cards.length,Math.min(4,count-page*4));
      seen.push(...cards.map(p=>p.product_id));
      ui.select(page*4); assert.ok(detailRows(items[ui.selected]).length);
      ui.move(1);
    }
    assert.deepEqual(seen,items.map(p=>p.product_id));
    assert.equal(ui.page,Math.ceil(count/4)-1);
    const h=initialState(); h.conversations[0].messages.push(message('assistant','reply',{products:items,effective_count:count}));
    assert.deepEqual(restore(serialize(h)).conversations[0].messages[0].products,items);
  }
});
