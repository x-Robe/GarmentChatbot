import { createRecognition, createPlayback, createSpeakerButton, speechText } from './voice.js';
import { applySearchState, referenceForRequest, persistState } from './state.js?v=frontend-cleanup-1';
import { contextBeforeReply } from './context.js?v=frontend-cleanup-1';
import { createProductResults } from './products.js?v=pagination-1';
import { assistantDisplayText, userDisplayText } from './presentation.js?v=frontend-cleanup-1';
import { searchReferences, searchImage, submissionPlan, ChatError } from './search.js?v=frontend-cleanup-1';
import { STORAGE_KEY, newId, now, createConversation, initialState, titleFor, message, serialize, restore, validateFile, MAX_ATTACHMENTS } from './state.js?v=frontend-cleanup-1';

const $ = selector => document.querySelector(selector);
const messages = $('#messages');
const queryInput = $('#query');
const conversation = $('#conversation');
const drawer = $('#history-drawer');
const previews = new Map(); // Session-only thumbnails; never persisted.
const sourceFiles = new Map(); // Original Files for pending image submissions/retries only.
let state = initialState();
let draft = [];
let pending = null;
let storageReadable = true;
let voiceMode = false; // Session-only; never saved with conversation data.
let speechRevision = 0;


function voiceBlocked() {
  if (playback.activeId) return 'Stop the spoken reply or wait for it to finish before using the microphone.';
  if (pending) return 'Wait for the current response before using voice input.';
  if (queryInput.value.trim() || draft.length) return 'Send or clear your draft and attachments before using voice input.';
  return '';
}
function updateSpeakers() {
  messages.querySelectorAll('[data-speech-id]').forEach(button => {
    const active = button.dataset.speechId === playback.activeId;
    button.classList.toggle('speaking', active);
    button.setAttribute('aria-pressed', String(active));
    button.setAttribute('aria-label', active ? 'Stop reading response' : 'Read response aloud');
    button.title = active ? 'Stop reading response' : 'Read response aloud';
  });
}
const playback = createPlayback({ platform: window, changed: () => { updateSpeakers(); updateVoiceAvailability(); }, notice: text => notice('#voice-status', text) });
let voiceBlockNotice = '';
const voice = createRecognition({
  platform: window, blocked: voiceBlocked,
  submit: text => submitMessage(text, state.mode, [], { voice: true }),
  recover: text => { if (!queryInput.value.trim() && !draft.length) { queryInput.value = text; updateComposer(); } },
  changed: value => {
    notice('#voice-status', value.text);
    $('#microphone').classList.toggle('listening', value.active);
    $('#microphone').setAttribute('aria-pressed', String(value.active));
    $('#microphone').setAttribute('aria-label', value.active ? 'Cancel voice input' : 'Start voice input');
    updateVoiceAvailability(false);
  },
});
function updateVoiceAvailability(showReason = true) {
  const reason = !voice.supported ? 'Voice input is unavailable in this browser. Please type your message.' : voiceBlocked();
  $('#microphone').disabled = !voice.active && !!reason;
  $('#microphone').title = voice.active ? 'Cancel voice input' : reason || 'Start voice input';
  if (showReason) {
    if (reason && !voice.active) notice('#voice-status', reason);
    else if ($('#voice-status').textContent === voiceBlockNotice) notice('#voice-status');
    voiceBlockNotice = reason;
  }
}
function stopVoice() { speechRevision++; voice.cancel(''); playback.stop(); }
function updateVoiceMode() {
  const button = $('#voice-mode');
  button.disabled = !playback.supported;
  button.setAttribute('aria-pressed', String(voiceMode));
  button.textContent = `Voice Mode: ${voiceMode ? 'On' : 'Off'}`;
  button.title = playback.supported ? 'Automatically read replies to voice submissions' : 'Voice Mode is unavailable because speech playback is not supported in this browser.';
}

function escape(value) { return String(value).replace(/[&<>"']/g, char => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[char])); }
function notice(selector, text = '') { $(selector).textContent = text; $(selector).hidden = !text; }
function announce(text) { $('#announcement').textContent = text; }
function activeChat() { return state.conversations.find(chat => chat.id === state.activeId); }
function save() {
  if (!storageReadable) return;
  if (persistState(localStorage, state)) notice('#storage-error');
  else notice('#storage-error', 'History and image continuation could not be saved in this browser. Keep this page open; refreshing may lose the reference.');
}
try {
  const raw = localStorage.getItem(STORAGE_KEY);
  if (raw) state = restore(raw);
} catch {
  storageReadable = false; // Preserve an unreadable record rather than overwriting it.
  notice('#storage-error', 'Saved history could not be opened. This session will stay in memory only.');
}
function updateComposer() {
  queryInput.style.height = 'auto';
  queryInput.style.height = `${Math.min(queryInput.scrollHeight, 140)}px`;
  $('.modes').disabled = false;
  $('.modes').title = 'Mode applies to text and image searches. More results keeps the previous search mode.';
  updateVoiceAvailability();
  $('#send').disabled = !!pending || (!queryInput.value.trim() && !draft.length);
  messages.querySelectorAll('.reply-action').forEach(button => { button.disabled = !!pending; });
}
function attachmentMarkup(attachment, removable = false) {
  const url = previews.get(attachment.id);
  const isImage = attachment.type.startsWith('image/');
  return `<div class="attachment-chip" title="${escape(attachment.name)}">${isImage && url ? `<img src="${url}" alt="${escape(attachment.name)}">` : `<span class="file-icon">${isImage ? 'IMAGE' : 'FILE'}</span>`}<div><div class="attachment-name">${escape(attachment.name)}</div><span class="attachment-detail">${Math.max(1, Math.round(attachment.size / 1024))} KB${isImage && !url ? ' · Preview not retained' : ''}</span></div>${removable ? `<button type="button" class="remove-attachment" data-remove="${escape(attachment.id)}" aria-label="Remove ${escape(attachment.name)}">×</button>` : ''}</div>`;
}
function attachThumbnailFallbacks(root) {
  root.querySelectorAll('.attachment-chip img').forEach(image => image.addEventListener('error', () => {
    const fallback = document.createElement('span'); fallback.className = 'file-icon'; fallback.textContent = 'IMAGE';
    image.replaceWith(fallback);
  }, { once: true }));
}
function renderDraft() {
  $('#draft-attachments').hidden = !draft.length;
  $('#draft-attachments').innerHTML = draft.map(a => attachmentMarkup(a, true)).join('');
  attachThumbnailFallbacks($('#draft-attachments'));
  updateComposer();
}
function clearDraft() {
  draft.forEach(a => { if (previews.has(a.id)) URL.revokeObjectURL(previews.get(a.id)); previews.delete(a.id); sourceFiles.delete(a.id); });
  draft = [];
  queryInput.value = '';
  notice('#attachment-error');
  renderDraft();
}
function renderConversation() {
  const chat = activeChat();
  if (chat.reference_warning) notice('#attachment-error', 'The saved image reference is unavailable. Upload it again to continue image searches.');
  $('.empty-state').hidden = chat.messages.length > 0;
  conversation.hidden = !chat.messages.length;
  messages.replaceChildren();
  let turn;
  for (const [index, entry] of chat.messages.entries()) {
    if (entry.role === 'user') {
      const userText = userDisplayText(entry, chat.messages[index + 1]?.request);
      turn = document.createElement('section');
      turn.className = 'turn';
      turn.setAttribute('aria-label', 'Conversation turn');
      turn.innerHTML = `<div class="user-message" aria-label="You"><div class="user-content">${entry.attachments?.length ? `<div class="attachments">${entry.attachments.map(a => attachmentMarkup(a)).join('')}</div>` : ''}${userText ? `<p>${escape(userText)}</p>` : ''}</div></div>`;
      messages.append(turn);
      continue;
    }
    if (!turn) { turn = document.createElement('section'); turn.className = 'turn'; messages.append(turn); }
    const reply = document.createElement('div');
    reply.className = 'assistant-message';
    reply.setAttribute('role', 'region');
    reply.setAttribute('aria-label', 'Garment response');
    if (entry.search_strategy) reply.dataset.searchStrategy = entry.search_strategy;
    if (entry.intent) reply.dataset.intent = entry.intent;
    if (entry.relation_to_context) reply.dataset.relationToContext = entry.relation_to_context;
    if (entry.resolved_query) reply.dataset.resolvedQuery = entry.resolved_query;
    reply.dataset.productCount = String(entry.products?.length || 0);
    if (entry.effective_count != null) reply.dataset.effectiveCount = String(entry.effective_count);
    if (entry.requested_count != null) reply.dataset.requestedCount = String(entry.requested_count);
    if (entry.status === 'pending') {
      reply.setAttribute('aria-busy', 'true');
      reply.innerHTML = `<p class="loading-copy">${entry.request?.type === 'image' ? 'Searching visually similar designs…' : 'Thinking…'}</p><div class="results" style="--columns:3" aria-hidden="true"><div class="skeleton"></div><div class="skeleton"></div><div class="skeleton"></div></div>`;
    } else {
      reply.innerHTML = `<p>${escape(assistantDisplayText(entry.text))}</p>${entry.attachmentNotice ? '<p class="attachment-notice">Attachments are kept in this chat only. These results use your text, not the sourceFiles.</p>' : ''}`;
      if (entry.products?.length) {
        const results = createProductResults(entry.products, entry.id);
        reply.querySelector('p').after(results);
        if (entry.closing_text) {
          const closing = document.createElement('p');
          closing.className = 'assistant-closing';
          closing.textContent = assistantDisplayText(entry.closing_text);
          results.after(closing);
        }
      }
      if (['error', 'interrupted'].includes(entry.status) && entry.request &&
          (entry.request.type !== 'image' || sourceFiles.has(entry.request.attachment_id))) {
        const retry = document.createElement('button'); retry.className = 'reply-action'; retry.textContent = 'Retry';
        retry.addEventListener('click', () => loadReply(chat, entry)); reply.append(retry);
      } else if (entry.status === 'empty' && entry.request?.mode === 'exact' && entry.request.type !== 'image') {
        const similar = document.createElement('button'); similar.className = 'reply-action'; similar.textContent = 'Try Similar';
        similar.addEventListener('click', () => { state.mode = 'similar'; syncMode(); submitMessage(entry.request.query, 'similar', []); }); reply.append(similar);
      }

    }
    const speaker = createSpeakerButton(document, entry, playback, () => { if (voice.active) voice.cancel('Voice input canceled to read the response aloud.'); });
    if (speaker) reply.append(speaker);
    turn.append(reply);
  }
  updateSpeakers();
  attachThumbnailFallbacks(messages);
  updateComposer();
}
async function loadReply(chat, entry, autoSpeak = false) {
  if (pending) return;
  stopVoice();
  // Snapshot before this request so retry never includes later messages or itself.
  if (entry.request.type !== 'image' && !entry.request.context) entry.request.context = contextBeforeReply(chat.messages, entry.id);
  const job = { controller: new AbortController(), chat, entry, autoSpeak: autoSpeak && voiceMode, speechRevision };
  pending = job;
  entry.status = 'pending'; entry.products = []; entry.text = ''; entry.closing_text = '';
  save(); renderConversation();
  conversation.scrollTop = conversation.scrollHeight;
  announce(entry.request.type === 'image' ? 'Searching visually similar designs…' : 'Preparing a response.');
  try {
    const response = entry.request.type === 'image'
      ? await searchImage({ file: sourceFiles.get(entry.request.attachment_id), query: entry.request.query, mode: entry.request.mode || 'auto', signal: job.controller.signal })
      : await searchReferences({ ...entry.request, reference_image: referenceForRequest(chat, entry.request), signal: job.controller.signal });
    if (job.controller.signal.aborted) return;
    const items = response.products;
    entry.products = items;
    if (entry.request.type === 'image') sourceFiles.delete(entry.request.attachment_id);
    entry.search_type = response.search_type;
    for (const key of ['requested_mode', 'effective_mode', 'effective_image_strategy']) {
      if (response[key] != null) entry[key] = response[key];
    }
    entry.response_id = response.response_id;
    entry.search_results = response.search_results;
    entry.closing_text = response.closing_text || '';
    entry.search_strategy = response.search_strategy;
    entry.intent = response.intent;
    entry.resolved_query = response.resolved_query;
    entry.status = items.length || (response.intent && response.intent !== 'search') ? 'complete' : 'empty';
    entry.text = response.text;
    entry.relation_to_context = response.relation_to_context;
    entry.has_more = response.has_more;
    for (const key of ['requested_count', 'effective_count', 'count_capped']) entry[key] = response[key];
    applySearchState(chat, entry, response);
    if (chat.reference_warning) notice('#attachment-error', 'Image continuation could not be saved. Upload the reference again for later changes.');
    announce(items.length ? `${items.length} T-shirt references found.` : response.intent && response.intent !== 'search' ? 'Response ready.' : 'No matching references.');
  } catch (error) {
    if (job.controller.signal.aborted) return;
    entry.status = 'error'; entry.text = error instanceof ChatError || error.message?.startsWith('The reference for this request') ? error.message : "Sorry, I couldn't complete that search. Please try again.";
    announce('Could not load references. Retry or select the image again.');
  } finally {
    if (pending === job) {
      pending = null; chat.updatedAt = now(); save(); renderConversation();
      // Only the successful rendered reply for this live voice request may speak.
      // Revision invalidation also prevents OFF→ON or chat-switch stale playback.
      if (job.autoSpeak && voiceMode && job.speechRevision === speechRevision &&
          !job.controller.signal.aborted && state.activeId === chat.id &&
          chat.messages.at(-1) === entry && ['complete', 'empty'].includes(entry.status)) {
        voice.cancel('');
        playback.play(entry.id, speechText(entry));
      }
    }
  }
}
function submitMessage(query = queryInput.value.trim(), mode = state.mode, attachments = draft, options = {}) {
  if (pending || (!query.trim() && !attachments.length)) return false;
  let plan;
  try { plan = submissionPlan(query, attachments); }
  catch (error) { notice('#attachment-error', error.message); announce(error.message); return false; }
  const chat = activeChat();
  const included = attachments.map(a => ({ ...a }));
  if (!chat.messages.length) chat.title = titleFor(query, included);
  chat.messages.push(message('user', query,
    { attachments: included, ...(plan.type === 'image' ? { search_type: 'image' } : {}) }));
  chat.updatedAt = now();
  if (attachments === draft) { draft = []; queryInput.value = ''; renderDraft(); }
  notice('#attachment-error');
  const entry = message('assistant', '', { status: 'complete', products: [],
    ...(plan.type === 'image' ? { search_type: 'image' } : {}) });
  entry.request = plan.type === 'image'
    ? { type: 'image', attachment_id: included[0].id, file_name: included[0].name, query, mode }
    : { query, mode, active_search: chat.active_search ? structuredClone(chat.active_search) : null, reference_revision: chat.reference_image ? chat.reference_revision : null };
  chat.messages.push(entry);
  loadReply(chat, entry, options.voice === true);
  return true;
}

function interrupt() {
  if (!pending) return;
  pending.controller.abort();
  pending.entry.status = 'interrupted'; pending.entry.text = pending.entry.request?.type === 'image' ? 'This image search was interrupted. Select the original image again to retry.' : 'This search was interrupted. You can retry it.';
  pending.chat.updatedAt = now(); pending = null; save();
}
function syncMode() { document.querySelector(`[name="mode"][value="${state.mode}"]`).checked = true; }
function closeHistory() { drawer.close(); $('#open-history').setAttribute('aria-expanded', 'false'); }
function releaseUploads() {
  for (const url of previews.values()) URL.revokeObjectURL(url);
  previews.clear(); sourceFiles.clear();
}
function newChat() {
  stopVoice(); interrupt(); clearDraft(); releaseUploads();
  const chat = createConversation();
  // Empty conversations need not accumulate in the history list.
  state.conversations = state.conversations.filter(c => c.messages.length);
  state.conversations.push(chat); state.activeId = chat.id;
  save(); renderConversation(); closeHistory(); queryInput.focus(); announce('New conversation. Previous chats are saved.');
}
function dayGroup(date) {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const yesterday = new Date(today); yesterday.setDate(yesterday.getDate() - 1);
  const value = new Date(date);
  return value >= today ? 'Today' : value >= yesterday ? 'Yesterday' : 'Earlier';
}
function openHistory() {
  const list = $('#history-list'); list.replaceChildren();
  const chats = state.conversations.filter(c => c.messages.length).sort((a, b) => b.updatedAt.localeCompare(a.updatedAt));
  let previousGroup;
  if (!chats.length) list.innerHTML = '<p class="history-empty">No previous chats</p>';
  for (const chat of chats) {
    const group = dayGroup(chat.updatedAt);
    if (group !== previousGroup) { const heading = document.createElement('h2'); heading.className = 'history-group'; heading.textContent = group; list.append(heading); previousGroup = group; }
    const button = document.createElement('button'); button.className = 'history-item'; button.textContent = chat.title; button.title = chat.title;
    button.setAttribute('aria-current', String(chat.id === state.activeId));
    button.addEventListener('click', () => { stopVoice(); interrupt(); clearDraft(); releaseUploads(); state.activeId = chat.id; save(); renderConversation(); conversation.scrollTop = conversation.scrollHeight; closeHistory(); queryInput.focus(); });
    list.append(button);
  }
  $('#open-history').setAttribute('aria-expanded', 'true'); drawer.showModal();
}
function closeMenu(focus = false) { $('#attachment-menu').hidden = true; $('#attach').setAttribute('aria-expanded', 'false'); if (focus) $('#attach').focus(); }
function selectFiles(files) {
  speechRevision++; playback.stop();
  if (voice.active) voice.cancel('Voice input canceled because an attachment was selected.');
  const errors = [];
  for (const file of files) {
    const result = validateFile(file);
    if (result.error) { errors.push(`${file.name}: ${result.error}`); continue; }
    if (draft.length >= MAX_ATTACHMENTS) { errors.push('Attach up to 4 files per message.'); break; }
    const attachment = { id: newId(), name: file.name, type: result.type, size: file.size };
    if (result.type.startsWith('image/')) {
      previews.set(attachment.id, URL.createObjectURL(file));
      sourceFiles.set(attachment.id, file);
    }
    draft.push(attachment);
  }
  notice('#attachment-error', errors.join(' ')); renderDraft();
}
$('#message-form').addEventListener('submit', event => { event.preventDefault(); submitMessage(); });
queryInput.addEventListener('input', () => { speechRevision++; playback.stop(); if (voice.active) voice.cancel('Voice input canceled because you started typing.'); updateComposer(); });
$('#microphone').addEventListener('click', () => { voice.toggle(); });
$('#voice-mode').addEventListener('click', () => {
  if (!playback.supported) return;
  voiceMode = !voiceMode;
  if (!voiceMode) stopVoice();
  updateVoiceMode();
  announce(`Voice Mode ${voiceMode ? 'on. Voice replies will be read aloud.' : 'off.'}`);
});
queryInput.addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing) { event.preventDefault(); submitMessage(); } });
document.querySelectorAll('[name="mode"]').forEach(input => input.addEventListener('change', () => { state.mode = input.value; save(); }));
$('#new-chat').addEventListener('click', newChat);
$('#drawer-new').addEventListener('click', newChat);
$('#open-history').addEventListener('click', openHistory);
$('#close-history').addEventListener('click', closeHistory);
drawer.addEventListener('close', () => $('#open-history').setAttribute('aria-expanded', 'false'));
for (const modal of [drawer]) modal.addEventListener('click', event => {
  if (event.target !== modal) return;
  const rect = modal.getBoundingClientRect();
  if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) modal.close();
});
$('#attach').addEventListener('click', () => { const open = $('#attachment-menu').hidden; $('#attachment-menu').hidden = !open; $('#attach').setAttribute('aria-expanded', String(open)); if (open) $('#choose-image').focus(); });
$('#choose-image').addEventListener('click', () => { closeMenu(); $('#file-input').click(); });
$('#file-input').addEventListener('change', event => { selectFiles(event.target.files); event.target.value = ''; });
document.addEventListener('click', event => { if (!event.target.closest('.attach-control')) closeMenu(); });
document.addEventListener('keydown', event => { if (event.key === 'Escape' && !$('#attachment-menu').hidden) { event.preventDefault(); closeMenu(true); } });
$('#draft-attachments').addEventListener('click', event => {
  const id = event.target.closest('[data-remove]')?.dataset.remove;
  if (!id) return;
  if (previews.has(id)) URL.revokeObjectURL(previews.get(id)); previews.delete(id); sourceFiles.delete(id);
  draft = draft.filter(a => a.id !== id); notice('#attachment-error'); renderDraft(); $('#attach').focus();
});
let dragDepth = 0;
const composer = $('#message-form');
composer.addEventListener('dragenter', event => { if (event.dataTransfer.types.includes('Files')) { event.preventDefault(); dragDepth++; composer.classList.add('drag-over'); } });
composer.addEventListener('dragover', event => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); });
composer.addEventListener('dragleave', () => { if (--dragDepth <= 0) { dragDepth = 0; composer.classList.remove('drag-over'); } });
composer.addEventListener('drop', event => { event.preventDefault(); dragDepth = 0; composer.classList.remove('drag-over'); selectFiles(event.dataTransfer.files); });
// Dropping outside the composer must not navigate away from saved chats.
window.addEventListener('dragover', event => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); });
window.addEventListener('drop', event => { if (event.dataTransfer.types.includes('Files')) event.preventDefault(); });
window.addEventListener('pagehide', () => { stopVoice(); releaseUploads(); });
window.addEventListener('pageshow', event => { if (event.persisted) { renderDraft(); renderConversation(); } });
updateVoiceMode(); syncMode(); renderConversation(); conversation.scrollTop = conversation.scrollHeight;

