import { contextText } from './context.js';

const errors = {
  'not-allowed': 'Microphone access was denied. Allow microphone access in your browser settings, or type your message.',
  'service-not-allowed': 'Speech recognition is not allowed in this browser. Please type your message.',
  'no-speech': "I couldn't detect any speech. Please try again.",
  'audio-capture': 'No microphone is available. Check your microphone, or type your message.',
  network: 'The speech service could not connect. Please try again or type your message.',
  aborted: 'Voice input was interrupted. No message was sent.',
};

// UI-only state. Nothing here is saved to conversation history or sent to a speech backend.
export function createRecognition({ platform, blocked, submit, recover, changed = () => {} }) {
  const Recognition = platform.SpeechRecognition || platform.webkitSpeechRecognition;
  let session = null;
  const supported = typeof Recognition === 'function';
  const emit = (status, text) => changed({ status, text, active: !!session, supported });
  function cancel(text = 'Voice input canceled. No message was sent.') {
    const old = session;
    session = null; // Invalidate before abort(), which may synchronously emit events.
    if (old) { try { old.recognition.abort(); } catch {} }
    emit('idle', text);
  }
  function toggle() {
    if (session) { cancel(); return; }
    if (!supported) { emit('idle', 'Voice input is unavailable in this browser. Please type your message.'); return; }
    const reason = blocked();
    if (reason) { emit('idle', reason); return; }
    const current = { recognition: null, finals: new Map(), done: false };
    try {
      current.recognition = new Recognition();
      const recognition = current.recognition;
      session = current;
      recognition.lang = 'en-US'; recognition.continuous = false; recognition.interimResults = true;
      const valid = () => session === current && !current.done;
      recognition.onstart = () => { if (valid()) emit('listening', 'Listening… Click the microphone again to cancel.'); };
      recognition.onresult = event => {
        if (!valid()) return;
        for (let i = event.resultIndex; i < event.results.length; i++) {
          if (event.results[i].isFinal) current.finals.set(i, event.results[i][0].transcript);
        }
      };
      recognition.onspeechend = () => { if (valid()) emit('finalizing', 'Finishing voice input… Click the microphone to cancel.'); };
      recognition.onerror = event => {
        if (!valid()) return;
        cancel(errors[event.error] || 'Speech recognition failed. Please try again or type your message.');
      };
      recognition.onend = () => {
        if (!valid()) return;
        current.done = true; session = null;
        const text = [...current.finals.entries()].sort((a,b) => a[0]-b[0]).map(([,value]) => value).join(' ').trim();
        if (!text) { emit('idle', errors['no-speech']); return; }
        if (text.length > 500) { recover(text); emit('idle', 'Voice input was not sent because it exceeds 500 characters. Shorten it and send it as text.'); return; }
        const reason = blocked();
        if (reason) { recover(text); emit('idle', `Voice input was not sent. ${reason} Recognized: ${text}`); return; }
        emit('submitting', 'Sending voice message…');
        // This is the ONLY submission site; neither result nor speechend sends.
        if (submit(text) === false) {
          recover(text); emit('idle', `Voice input was not sent. Recognized: ${text}`);
        } else emit('idle', 'Voice message sent.');
      };
      emit('listening', 'Starting microphone… Click again to cancel.');
      recognition.start();
    } catch { cancel('Could not start voice input. Please check microphone access or type your message.'); }
  }
  return { supported, toggle, cancel, get active() { return !!session; } };
}

export function speechText(entry) {
  const clean = value => {
    if (typeof value !== 'string') return '';
    try { JSON.parse(value); return ''; } catch {} // Never read raw JSON.
    return contextText(value.replace(/```[\s\S]*?```/g, ''))
      .split('\n').filter(line => !/^\s*(?:[{\[]|[}\]]|[-*]?\s*"[^"\n]+"\s*:|(?:colors?|patterns?|neckline|sleeve|style|category|buttons|attributes)\s*:|.*\b(?:similarity_score|label_matches|response_id|score|product id|point id)\b)/i.test(line))
      .filter(line => !entry.products?.length || !/^\s*(?:\d+[.)]\s|[-*]\s)/.test(line))
      .map(line => line.replace(/\[([^\]]+)\]\([^)]*\)/g, '$1').replace(/^\s*(?:\d+[.)]\s|[-*]\s)/, '').replace(/[*#`]/g, '').trim()).filter(Boolean).join(' ').trim();
  };
  const main = clean(entry.text), closing = clean(entry.closing_text);
  // Product metadata is never used for speech. Use a short summary if only lists remain.
  const parts = main ? [main] : entry.products?.length ? [`I found ${entry.products.length} matching designs for you.`] : [];
  if (closing && !parts.some(text => text.toLowerCase().includes(closing.toLowerCase()))) {
    if (main && closing.toLowerCase().includes(main.toLowerCase())) parts.splice(0, parts.length, closing);
    else parts.push(closing);
  }
  return parts.join(' ');
}

export function createPlayback({ platform, changed = () => {}, notice = () => {} }) {
  const synth = platform.speechSynthesis;
  const supported = !!synth && typeof synth.speak === 'function' && typeof synth.cancel === 'function' && typeof platform.SpeechSynthesisUtterance === 'function';
  let active = null;
  function stop() {
    const old = active; active = null;
    if (supported && old) { try { synth.cancel(); } catch {} }
    changed(null);
  }
  function play(id, text) {
    if (!supported || !text.trim()) return;
    stop();
    try {
      const utterance = new platform.SpeechSynthesisUtterance(text);
      utterance.lang = 'en-US'; utterance.rate = 1;
      const current = { id, utterance }; active = current; changed(id);
      utterance.onstart = () => { if (active === current) changed(id); };
      utterance.onend = () => { if (active === current) { active = null; changed(null); } };
      utterance.onerror = () => { if (active === current) { active = null; changed(null); notice('Could not read this response aloud. Please try again.'); } };
      synth.speak(utterance);
    } catch { stop(); notice('Speech playback is unavailable. Please try again.'); }
  }
  function toggle(id, text) {
    if (active?.id === id) stop();
    else play(id, text);
  }
  return { supported, play, toggle, stop, get activeId() { return active?.id ?? null; } };
}

export const speakerIcon = '<svg viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M11 5 6 9H3v6h3l5 4V5ZM15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/></svg>';
export function createSpeakerButton(document, entry, playback, beforePlay = () => {}) {
  const text = speechText(entry);
  if (!playback.supported || !text || !['complete', 'empty'].includes(entry.status)) return null;
  const button = document.createElement('button');
  button.type = 'button'; button.className = 'icon-button speaker-button'; button.dataset.speechId = entry.id;
  button.innerHTML = speakerIcon;
  button.setAttribute('aria-label', 'Read response aloud'); button.setAttribute('aria-pressed', 'false'); button.title = 'Read response aloud';
  button.addEventListener('click', () => { beforePlay(); playback.toggle(entry.id, text); });
  return button;
}
