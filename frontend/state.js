export const STORAGE_KEY = 'garment.conversations.v1';
export const MODES = ['auto', 'exact', 'similar'];
export const newId = () => crypto.randomUUID();
export const now = () => new Date().toISOString();
export function createConversation() {
  const timestamp = now();
  return { id: newId(), title: 'New chat', createdAt: timestamp, updatedAt: timestamp, messages: [], active_search: null, reference_image: null, reference_revision: null };
}
export function initialState() {
  const chat = createConversation();
  return { version: 1, activeId: chat.id, mode: 'auto', conversations: [chat] };
}
export function titleFor(text, attachments = []) {
  const value = text.trim().replace(/\s+/g, ' ');
  if (!value) return attachments.some(a => a.type.startsWith('image/')) ? 'Image reference' : 'Uploaded reference';
  const title = value.charAt(0).toUpperCase() + value.slice(1);
  return title.length > 40 ? title.slice(0, 39).trimEnd() + '…' : title;
}
export function message(role, text, extras = {}) {
  return { id: newId(), role, text, timestamp: now(), attachments: [], ...extras };
}
export function serialize(state) {
  // Context is rebuilt from messages on retry; do not duplicate full history.
  // File contents and temporary blob URLs must never enter localStorage.
  return JSON.stringify(state, (key, value) => ['previewUrl', 'file', 'context'].includes(key) ? undefined : value);
}
export function restore(raw) {
  const state = JSON.parse(raw);
  if (state?.mode === 'default') state.mode = 'auto';
  if (state?.version !== 1 || !Array.isArray(state.conversations) || !MODES.includes(state.mode)) throw new Error('Invalid saved history');
  for (const chat of state.conversations) {
    if (!chat || typeof chat.id !== 'string' || typeof chat.title !== 'string' || !Number.isFinite(Date.parse(chat.updatedAt)) || !Array.isArray(chat.messages)) throw new Error('Invalid conversation');
    if (chat.reference_image && !validReference(chat.reference_image)) {
      chat.reference_image = null;
      chat.reference_warning = true;
    }
    chat.reference_image ??= null;
    const hadSearchState = Object.hasOwn(chat, 'active_search');
    chat.active_search = validActiveSearch(chat.active_search) ? chat.active_search : null;
    if (!hadSearchState) {
      const lastSearch = [...chat.messages].reverse().find(e =>
        ['complete','empty'].includes(e.status) && !['unrelated','informational','clarification'].includes(e.intent) &&
        (e.search_type === 'image' || e.products?.length));
      if (lastSearch?.search_type === 'image') chat.active_search = {search_type:'image'};
    }
    for (const entry of chat.messages) {
      if (!entry || typeof entry.id !== 'string' || !['user', 'assistant'].includes(entry.role) || typeof entry.text !== 'string') throw new Error('Invalid message');
      if (entry.attachments && (!Array.isArray(entry.attachments) || entry.attachments.some(a => !a || typeof a.id !== 'string' || typeof a.name !== 'string' || typeof a.type !== 'string' || !Number.isFinite(a.size)))) throw new Error('Invalid attachment');
      if (entry.products && (!Array.isArray(entry.products) || entry.products.some(p => !p || typeof p.image !== 'string' || typeof p.title !== 'string' || !p.attributes || typeof p.attributes !== 'object'))) throw new Error('Invalid product');
      if (entry.request?.mode === 'default') entry.request.mode = 'auto';
      if (entry.request?.type === 'image' && (typeof entry.request.attachment_id !== 'string' || typeof entry.request.file_name !== 'string' || (entry.request.query != null && typeof entry.request.query !== 'string'))) throw new Error('Invalid image request');
      if (entry.request && entry.request.type !== 'image' && (typeof entry.request.query !== 'string' || !MODES.includes(entry.request.mode))) throw new Error('Invalid request');
      if (entry.status === 'pending') {
        entry.status = 'interrupted';
        entry.text = entry.request?.type === 'image' ? 'This image search was interrupted. Select the original image again to retry.' : 'This search was interrupted. You can retry it.';
      }
    }
  }
  if (!state.conversations.some(chat => chat.id === state.activeId)) {
    const chat = createConversation();
    state.conversations.push(chat);
    state.activeId = chat.id;
  }
  return state;
}
export const MAX_FILE_SIZE = 10 * 1024 * 1024;
export const MAX_ATTACHMENTS = 4;
const types = { jpg: 'image/jpeg', jpeg: 'image/jpeg', png: 'image/png', webp: 'image/webp' };
export function validateFile(file) {
  const type = types[file.name.split('.').pop().toLowerCase()];
  if (!type || (file.type && file.type !== type)) return { error: 'Choose a JPG, PNG or WebP image.' };
  if (file.size > MAX_FILE_SIZE) return { error: 'Files must be 10 MiB or smaller.' };
  if (!file.size) return { error: 'This file is empty. Choose another file.' };
  return { type };
}


export function validActiveSearch(value) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false;
  const keys = ['text_overrides','effective_filters','search_type','resolved_query','mode','effective_image_strategy','search_strategy','attributes','shown_product_ids','shown_point_ids'];
  if (Object.keys(value).some(key => !keys.includes(key))) return false;
  if (value.search_type === 'image' && value.text_overrides) return validImageState(value);
  if (value.search_type === 'image') return !value.resolved_query &&
    !Object.keys(value.attributes || {}).length && !value.shown_product_ids?.length && !value.shown_point_ids?.length;
  return value.search_type === 'text' && typeof value.resolved_query === 'string' &&
    value.resolved_query.length > 0 && value.resolved_query.length <= 2000 &&
    MODES.includes(value.mode) && ['exact','similar','both'].includes(value.search_strategy) &&
    value.attributes && typeof value.attributes === 'object' && !Array.isArray(value.attributes) &&
    ['shown_product_ids','shown_point_ids'].every(key => Array.isArray(value[key]) &&
      value[key].length <= 4096 && value[key].every(id => typeof id === 'string' && id.length > 0 && id.length <= 128));
}

export function applySearchState(chat, entry, response) {
  // A retried historical message must not overwrite a newer topic's active state.
  if (chat.messages.at(-1) !== entry) return;
  if (entry.request?.type === 'image') {
    if (!['unrelated','clarification'].includes(response.intent) ||
        (response.effective_image_strategy === 'attributes_required' && validReference(response.image_reference))) {
      chat.active_search = validActiveSearch(response.active_search) ? structuredClone(response.active_search) : {search_type:'image'};
      chat.reference_image = validReference(response.image_reference) ? structuredClone(response.image_reference) : null;
      chat.reference_revision = newId();
      chat.reference_warning = !chat.reference_image;
    }
  } else if (Object.hasOwn(response, 'active_search')) {
    chat.active_search = validActiveSearch(response.active_search) ? structuredClone(response.active_search) : null;
  }
}


export function validReference(value) {
  if (!value || value.version !== 1 || value.dimension !== 512 || typeof value.model !== 'string' ||
      !value.model || value.model.length > 200 || !Array.isArray(value.embedding) || value.embedding.length !== 512 ||
      !value.embedding.every(v => typeof v === 'number' && Number.isFinite(v)) ||
      !value.image_analysis || typeof value.image_analysis !== 'object' || Array.isArray(value.image_analysis)) return false;
  const norm = Math.sqrt(value.embedding.reduce((sum,v) => sum+v*v,0));
  return norm >= .999 && norm <= 1.001 &&
    Object.keys(value).every(k => ['version','dimension','model','embedding','image_analysis'].includes(k));
}
function validImageState(value) {
  const strategies = ['attribute_guided', 'strict_attributes', 'pure_image_similarity', 'explicit_text_filtered_similarity', 'attributes_required'];
  return (value.mode == null || MODES.includes(value.mode)) &&
    (value.effective_image_strategy == null || strategies.includes(value.effective_image_strategy)) && ['text_overrides','effective_filters'].every(k => value[k] && typeof value[k] === 'object' && !Array.isArray(value[k])) &&
    ['shown_product_ids','shown_point_ids'].every(k => Array.isArray(value[k]) && value[k].length <= 4096 &&
      value[k].every(id => typeof id === 'string' && id.length > 0 && id.length <= 128));
}

export function referenceForRequest(chat, request) {
  if (!request.reference_revision) return null;
  if (request.reference_revision !== chat.reference_revision || !validReference(chat.reference_image))
    throw new Error('The reference for this request is no longer available. Please upload it again.');
  return chat.reference_image;
}

export function persistState(storage, state) {
  try { storage.setItem(STORAGE_KEY, serialize(state)); return true; }
  catch { return false; }
}
