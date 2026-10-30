import { API_BASE_URL } from './config.js';

export class ChatError extends Error {}
const failure = "Sorry, I couldn't complete that search. Please try again.";
const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);

export function resolveImageUrl(imageUrl) {
  if (typeof imageUrl !== 'string' || !imageUrl.trim()) return '';
  try {
    const url = new URL(imageUrl, `${API_BASE_URL.replace(/\/$/, '')}/`);
    return ['http:', 'https:'].includes(url.protocol) ? url.href : '';
  } catch { return ''; }
}

export function productView(product) {
  // Descriptive caption from real attributes, not an invented product name.
  const attributes = product.attributes || {};
  const tags = [];
  for (const key of ['style', 'patterns', 'neckline', 'sleeve', 'colors']) {
    const values = Array.isArray(attributes[key]) ? attributes[key] : [attributes[key]];
    const value = values.find(v => typeof v === 'string' && v.trim() &&
      !tags.some(tag => tag.toLowerCase() === v.toLowerCase()));
    if (value) tags.push(value);
    if (tags.length === 4) break;
  }
  const caption = tags.join(' · ');
  return { ...product, title: caption || 'Garment reference', image: resolveImageUrl(product.image_url), attributes };
}

export async function searchReferences({ query, mode, context, active_search, reference_image, signal }) {
  let response;
  try {
    response = await fetch(new URL(reference_image ? '/api/image-search/continue' : '/api/chat', API_BASE_URL), {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query, mode, ...(reference_image ? { reference_image } : {}), ...(context?.length ? { context } : {}), ...(active_search ? { active_search } : {}) }), signal,
    });
  } catch (error) {
    if (signal?.aborted || error.name === 'AbortError') throw error;
    throw new ChatError('Cannot connect to the Garment backend. Make sure the API server is running.');
  }
  if (!response.ok) {
    if (reference_image && response.status === 422) throw new ChatError('Saved image context is invalid or incompatible. Please upload the reference image again.');
    if (reference_image && response.status === 413) throw new ChatError('This conversation request is too large. Please start a new chat.');
    throw new ChatError(failure);
  }
  let data;
  try { data = await response.json(); } catch { throw new ChatError(failure); }
  const validProduct = p => object(p) && object(p.attributes) &&
    (p.image_url == null || typeof p.image_url === 'string') &&
    (p.match_type == null || ['exact', 'similar'].includes(p.match_type));
  if (!object(data) || typeof data.text !== 'string' || typeof data.response_id !== 'string' ||
      (data.resolved_query != null && typeof data.resolved_query !== 'string') ||
      (data.closing_text != null && typeof data.closing_text !== 'string') ||
      (data.search_strategy != null && !['exact', 'similar', 'both', 'none'].includes(data.search_strategy)) ||
      (data.intent != null && !['search', 'informational', 'unrelated', 'clarification'].includes(data.intent)) ||
      !Array.isArray(data.products) || !data.products.every(validProduct) ||
      !object(data.search_results) || !['exact', 'similar'].every(kind =>
        Array.isArray(data.search_results[kind]) && data.search_results[kind].every(validProduct))) {
    throw new ChatError(failure);
  }
  return { ...data, products: data.products.map(productView) };
}

export function submissionPlan(query, attachments = []) {
  if (!attachments.length) return { type: 'text' };
  if (attachments.length !== 1) throw new ChatError('Please send one image at a time.');
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(attachments[0].type))
    throw new ChatError('Please upload a JPEG, PNG, or WebP image.');
  return { type: 'image' };
}

export async function searchImage({ file, query = '', mode = 'auto', signal }) {
  if (!file) throw new ChatError('Please select the original image again to retry this search.');
  if (!['image/jpeg', 'image/png', 'image/webp'].includes(file.type))
    throw new ChatError('Please upload a JPEG, PNG, or WebP image.');
  if (file.size > 10 * 1024 * 1024) throw new ChatError('That image is too large. Please use an image no larger than 10 MiB.');
  const body = new FormData();
  body.append('mode', mode);
  body.append('image', file); // API owns the default result count.
  if (query.trim()) body.append('query', query.trim());
  let response;
  try {
    response = await fetch(new URL('/api/image-search', API_BASE_URL), { method: 'POST', body, signal });
  } catch (error) {
    if (signal?.aborted || error.name === 'AbortError') throw error;
    throw new ChatError('Cannot connect to the Garment backend. Make sure the API server is running.');
  }
  if (!response.ok) {
    if (response.status === 413) throw new ChatError('That image is too large. Please use an image no larger than 10 MiB.');
    if (response.status === 400) {
      let detail;
      try { detail = (await response.json()).detail; } catch {}
      // Only map known API messages; never display arbitrary server content.
      if (detail === 'Image dimensions are too large (maximum 20 million pixels).')
        throw new ChatError('That image has too many pixels. Please use an image with at most 20 million pixels.');
      if (detail === 'Upload a JPEG, PNG, or WebP image.')
        throw new ChatError('Please upload a JPEG, PNG, or WebP image.');
      throw new ChatError("I couldn't read that image. Please try another file.");
    }
    if (response.status === 422) throw new ChatError('Please select a JPEG, PNG, or WebP image and try again.');
    throw new ChatError('Image search is temporarily unavailable. Please try again.');
  }
  let data;
  try { data = await response.json(); } catch { throw new ChatError(failure); }
  if (!object(data) || data.search_type !== 'image' || typeof data.text !== 'string' ||
      typeof data.closing_text !== 'string' || !Array.isArray(data.products) ||
      !data.products.every(p => object(p) && object(p.attributes) && ['exact', 'similar'].includes(p.match_type) &&
        (p.image_url == null || typeof p.image_url === 'string'))) throw new ChatError(failure);
  return { ...data, products: data.products.map(productView) };
}
