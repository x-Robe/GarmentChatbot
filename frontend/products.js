import { productView } from './search.js';

export const PAGE_SIZE = 4;
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const humanize = value => value.charAt(0).toUpperCase() + value.slice(1);
export const matchLabel = product => ({exact:'Exact', similar:'Similar'}[product.match_type] || '');

export function detailRows(product) {
  const attributes = product.attributes || {};
  const rows = [];
  for (const [key, label] of [['colors','Color'],['style','Style'],['patterns','Pattern'],['neckline','Neckline'],['sleeve','Sleeve'],['buttons','Buttons'],['category','Category'],['material','Material']]) {
    const raw = attributes[key];
    let value;
    if (key === 'buttons' && typeof raw === 'boolean') value = raw ? 'Yes' : 'No';
    else value = (Array.isArray(raw) ? raw : [raw]).filter(v => typeof v === 'string' && v.trim()).map(v => humanize(v.trim())).join(' · ');
    if (value) rows.push([label, value]);
  }
  if (matchLabel(product)) rows.push(['Match', matchLabel(product)]);
  return rows;
}

export function carouselState(count) {
  return {
    page: 0, selected: null,
    get pages() { return Math.max(1, Math.ceil(count / PAGE_SIZE)); },
    move(delta) { this.page = Math.max(0, Math.min(this.pages - 1, this.page + delta)); this.selected = null; },
    select(index) {
      if (index >= this.page * PAGE_SIZE && index < Math.min(count, (this.page + 1) * PAGE_SIZE)) this.selected = index;
    },
  };
}
export const pageProducts = (products, page) => products.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);
function safeImage(value) {
  if (!value) return '';
  try { const url = new URL(value, location.href); return ['http:', 'https:'].includes(url.protocol) ? url.href : ''; }
  catch { return ''; }
}

// UI state belongs only to this rendered message; never written to chat history.
export function createProductResults(products, messageId) {
  const root = document.createElement('section');
  root.className = 'product-area';
  root.setAttribute('aria-label', 'Product results');
  const state = carouselState(products.length);
  const detailsId = `product-details-${messageId}`;
  function render(focus) {
    const start = state.page * PAGE_SIZE;
    const selected = state.selected === null ? null : products[state.selected];
    root.classList.toggle('has-selection', !!selected);
    root.innerHTML = `<div class="product-carousel"><div class="carousel-track">
      <button type="button" class="carousel-arrow previous" aria-label="Previous products" ${state.pages === 1 ? 'hidden' : ''} ${state.page === 0 ? 'disabled' : ''}>‹</button>
      <div class="product-row">${pageProducts(products, state.page).map((product, offset) => {
        const index = start + offset, image = safeImage(product.image), title = productView(product).title;
        return `<figure class="reference"><button type="button" class="image-button" data-product="${index}" data-product-id="${escape(product.product_id ?? '')}" data-point-id="${escape(product.point_id ?? '')}" aria-label="Show details for product ${index + 1}: ${escape(title)}" aria-controls="${escape(detailsId)}" aria-pressed="${index === state.selected}">${image ? `<img src="${escape(image)}" alt="${escape(title)}" width="600" height="720">` : '<span class="image-unavailable">Image unavailable</span>'}</button>${matchLabel(product) ? `<figcaption class="match-type">${matchLabel(product)}</figcaption>` : ''}</figure>`;
      }).join('')}</div>
      <button type="button" class="carousel-arrow next" aria-label="Next products" ${state.pages === 1 ? 'hidden' : ''} ${state.page === state.pages - 1 ? 'disabled' : ''}>›</button>
      </div><p class="carousel-position" aria-live="polite">${start + 1}–${Math.min(start + PAGE_SIZE, products.length)} of ${products.length}</p></div>
      <aside class="product-details" id="${escape(detailsId)}" aria-label="Product details" ${selected ? '' : 'hidden'}>${selected ? `<div class="detail-header"><h3>Product ${state.selected + 1}</h3><button type="button" class="detail-close" aria-label="Close product details">×</button></div><dl>${detailRows(selected).map(([label, value]) => `<div><dt>${escape(label)}</dt><dd>${escape(value)}</dd></div>`).join('')}</dl>${detailRows(selected).length ? '' : '<p class="detail-empty">No details available.</p>'}` : ''}</aside>`;
    root.querySelectorAll('[data-product]').forEach(button => {
      button.addEventListener('click', () => { state.select(Number(button.dataset.product)); render(`[data-product="${state.selected}"]`); });
      button.querySelector('img')?.addEventListener('error', () => { button.innerHTML = '<span class="image-unavailable">Image unavailable</span>'; }, { once: true });
    });
    for (const [name, delta] of [['previous', -1], ['next', 1]]) {
      root.querySelector(`.${name}`).addEventListener('click', () => {
        state.move(delta); render(`.${name}`);
        if (root.querySelector(`.${name}`).disabled) root.querySelector('[data-product]')?.focus({preventScroll:true});
      });
    }
    root.querySelector('.detail-close')?.addEventListener('click', () => { const index = state.selected; state.selected = null; render(`[data-product="${index}"]`); });
    if (focus) root.querySelector(focus)?.focus({preventScroll:true});
  }
  render();
  return root;
}
