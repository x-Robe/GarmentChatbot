// Full normal history; deterministic recent-text fallback for oversized chats.
import { userDisplayText } from './presentation.js?v=frontend-cleanup-1';
import { CONTEXT_LIMITS } from './config.js';
export const CONTEXT_MESSAGE_LIMIT = CONTEXT_LIMITS.messages;
export const CONTEXT_CHAR_LIMIT = CONTEXT_LIMITS.characters;
export const CONTEXT_TEXT_LIMIT = CONTEXT_LIMITS.perMessage;

export function contextText(value) {
  if (typeof value !== 'string') return '';
  return value
    .replace(/!\[[^\]\n]*\]\([^\n)]*\)/g, '')
    .replace(/https?:\/\/\S+|file:\/\/\S+/g, '')
    .replace(/(^|\s)(?:\/|data\/images\/|[A-Za-z]:[\\/])\S+/g, '$1')
    .replace(/^.*\b(?:point_id|product_id|image_path|image_url)\b.*$/gm, '')
    .replace(/data:[^\s]+/g, '')
    .replace(/^.*\b(?:embedding|vector|base64|api_key|authorization|tool_trace)\b.*$/gim, '')
    .trim().slice(-CONTEXT_TEXT_LIMIT);
}

export function recentContext(messages) {
  const turns = [];
  for (const entry of messages) {
    if (entry.role === 'user') turns.push([entry]);
    else if (entry.role === 'assistant' && turns.length) turns.at(-1).push(entry);
  }
  const records = turns.flatMap(turn => {
    if (turn.some(e => ['pending', 'error', 'interrupted'].includes(e.status))) return [];
    const user = turn[0];
    const assistant = turn.find(e => e.role === 'assistant');
    return [user, assistant].filter(Boolean).flatMap(entry => {
      const authoredText = entry.role === 'user' ? userDisplayText(entry, assistant?.request) : entry.text;
      const userText = entry.search_type === 'image' && entry.role === 'user'
        ? `Reference image search${authoredText ? `: ${authoredText}` : ''}` : authoredText;
      const text = contextText([userText, entry.role === 'assistant' ? entry.closing_text : '']
        .filter(value => typeof value === 'string').join('\n'));
      return text ? [{role: entry.role, text}] : [];
    });
  });
  let remaining = CONTEXT_CHAR_LIMIT;
  const bounded = [];
  for (const record of records.slice(-CONTEXT_MESSAGE_LIMIT).reverse()) {
    if (remaining <= 0) break;
    const text = record.text.slice(-remaining);
    bounded.push({...record, text}); remaining -= text.length;
  }
  return bounded.reverse();
}

export function contextBeforeReply(messages, replyId) {
  const replyIndex = messages.findIndex(entry => entry.id === replyId);
  if (replyIndex < 0) return [];
  let userIndex = replyIndex - 1;
  while (userIndex >= 0 && messages[userIndex].role !== 'user') userIndex--;
  return recentContext(messages.slice(0, Math.max(0, userIndex)));
}
