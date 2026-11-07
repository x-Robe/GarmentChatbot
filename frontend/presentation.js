// Display-only guard for accidental internal image references. Never parses products.
export function assistantDisplayText(text) {
  return text
    .replace(/!\[[^\]\n]*\]\(\s*(?:data\/images\/|\/images\/)[^\n)]*\)/g, '')
    .replace(/(^|[\s`(])(?:data\/images\/|\/images\/)[^\s`<>)]*\.(?:jpe?g|png|webp|gif|svg)(?=$|[\s`.,;!?)])/gim, '$1')
    .trim();
}

// Normalize only a legacy image label corroborated by the original upload request.
// New messages store authored text; history is never rewritten by this function.
export function userDisplayText(entry, request) {
  const text = entry.text;
  if (entry.role !== 'user' || entry.search_type !== 'image' || request?.type !== 'image'
      || typeof request.query !== 'string') return text;
  const attachment = entry.attachments?.find(a => a.id === request.attachment_id
    && a.name === request.file_name && a.type?.startsWith('image/'));
  if (!attachment) return text;
  const legacy = `Image search: ${attachment.name}${request.query ? ` — ${request.query}` : ''}`;
  return text === legacy ? request.query : text;
}
