> Historical engineering evidence copied for reference. Counts and live-service checks describe that stage, not a new production validation. Screenshots/debug outputs are intentionally omitted. Release-copy checks are in ../GITHUB_RELEASE_CHECKLIST.md.

# Voice input and read-aloud implementation / validation

Date: 2026-10-30 (Asia/Hong_Kong).

## Files

Modified: `index.html`, `app.js`, `styles.css`, `README.md`.
Added: `voice.js`, `voice.test.js`, `voice-app.test.js`, `VOICE_VALIDATION.md`.
No dependencies, backend endpoints, models, or retrieval code were added or changed.
A before/after SHA-256 comparison of backend root/source Python files and SKILL.md
found no changes during this task.

## Recognition and submission

`voice.js` detects `SpeechRecognition || webkitSpeechRecognition`. A new object
per session uses en-US, continuous=false and interimResults=true. The microphone
has accessible start/cancel labels, aria-pressed, a highlighted active state, and a
live status line. Both starting and finalizing remain cancelable.

Result events retain only final transcripts in an index-keyed Map; repeated result
events replace the same slot. Speech-end only changes the status. A normal end
captures the joined, trimmed text, invalidates the session, and submits exactly
once. No arbitrary timer or custom silence detection is used.

The sole submission callback is `submitMessage(text, state.mode, [])` in `app.js`.
It follows the same message rendering, persistence, context snapshot, active search,
image continuation where already applicable, API routing, count handling, and
pagination as typed text. It cannot include a pending image attachment. It creates
no separate voice retrieval path and does not interpret spoken count commands.
The existing submit function now returns a boolean indicating whether it accepted
submission; its search behavior remains unchanged.

The session-object identity and done flag reject stale events, repeated end calls,
and events from canceled or failed sessions. Cancellation invalidates the session
before aborting the browser, so synchronous abort/end events cannot send. Errors
also invalidate and abort. Friendly messages cover no speech, denied access,
service refusal, missing microphone, network failure, abort and unknown errors;
raw exception strings are not displayed. Constructor/start failures restore idle.

An existing draft, attachment, or pending request blocks activation. Typing or
selecting files during recognition cancels it and preserves the new draft/file.
If a completed transcript cannot be submitted because the composer became busy,
it is retained as an editable draft when the composer is empty, and is also shown
in the not-sent status. Existing drafts are preserved. Transcripts exceeding the
composer's 500-character limit are retained for editing without automatic send.
No conversation messages are saved until normal submission actually occurs.

New Chat, conversation selection, any actual request, and pagehide cancel
recognition and stop playback. Re-entering from the back/forward cache requires a
fresh microphone click. No recordings are stored.

## Synthesis

`SpeechSynthesis` and `SpeechSynthesisUtterance` are independently feature-detected.
Completed/empty assistant replies with meaningful speech text get a keyboard-
operable speaker button. Errors and pending replies do not. Speech uses en-US at
rate 1 and the browser's default available voice. Only explicit clicks start it.

Only sanitized assistant intro/closing text is used; product objects never feed
speech. Local paths, URLs, IDs, vector/debug lines, raw JSON, fenced payloads,
metadata rows and product bullet lists are suppressed. Informational explanations
(including their ordinary bullet text) are retained. Overlapping intro/closing
text is not repeated. If only a product list remains, a short summary uses the real
returned count. The visible assistant response is never rewritten for speech.

One active utterance is retained in memory. The same button cancels; another button
cancels the old utterance before starting the selected one. Identity checks prevent
old start/end/error events from changing newer playback state. Completion/error
restores the label and aria-pressed state. Synchronous playback errors also reset
state. The active button represents a pending/active speech request; it does not
assert that sound is actually audible on the user's hardware.

## Automated validation

Frontend: **82 passed, zero failures** (48 existing tests plus 34 additional test
records, including the application integration parent and six subtests).
Backend: **138 passed, zero failures**. Total: **220 passed**.

Commands:

```sh
# From frontend/:
node --test *.test.js

# From backend/:
PYTHONPATH=.:tests .venv/bin/python -m unittest test_chatbot_results test_api test_image_api test_image_text test_hybrid_image_search test_image_search test_extraction_robustness test_pagination test_image_context test_result_count
```

Speech APIs are mocked in Node tests. Coverage includes standard/prefixed/absent
APIs; start/listening; final/interim/multiple results; automatic single submission;
empty/no-speech/permission/network/hardware/abort errors; cancel and stale events;
draft, attachment and busy guards; transcript recovery; start failure; unchanged
count/pagination text in normal HTTP bodies; synthesis support/play/stop/switch;
stale playback events; error cleanup; speech content selection and accessible
speaker rendering.

The application integration test executes the actual `app.js` with a small DOM/event
fixture and mocked fetch/speech APIs. It exercises automatic submission without a
Send click, ordinary persisted user messages, draft and attachment preservation,
in-flight blocking, multiple speaker controls, New Chat, conversation switching,
and page exit. Mocked events establish logic behavior, not recognition accuracy or
audible output. Existing tests continue covering text/image/mixed requests,
context, storage, pagination, result counts, carousel and product details.

## Actual local browser checks

Frontend: http://127.0.0.1:8000/; backend: http://127.0.0.1:8001/.
Tested in the available in-app browser, not a separately verified Chrome session.

- Existing image-search conversation and product cards restored successfully.
- Microphone and per-message speaker controls rendered.
- Entering an unsent draft disabled the microphone with an explanation; clearing
  the draft restored it.
- Clicking the actual microphone entered the starting state. Clicking again
  canceled and restored idle, with no new user message. No final transcript from a
  human speaking into hardware was obtained; this is only an activation/cancel UI check.
- Clicking an actual speaker changed it to Stop reading response; clicking again
  restored Read response aloud. Audible sound was not independently verified.
- A typed live query, `Show me five black oversized T-shirts.`, returned five real
  products. The microphone was disabled while processing and restored afterward.
- A typed live follow-up, `Show me three more.`, returned three products. Their
  image paths differed from all five prior results, including the fifth carousel
  item. Effective counts were 5 then 3. This validates the existing live text
  flow, not live voice recognition.
- Carousel navigation and product details worked. Refresh restored both turns,
  counts and speaker controls without automatically playing speech.
- At 375px viewport width there was no document horizontal overflow; microphone
  and Send stayed within the composer. The viewport override was reset afterward.

New live image-only and image-plus-text searches were not repeated in this task;
those paths have automated regression coverage. No live permission-denial case was
forced; controlled errors were verified in mocked tests.

## Remaining hardware / hosting acceptance

A person must test on the demonstration device in a supported browser:

1. Click microphone, say `Show me five black oversized T-shirts.`, and stop.
   Confirm a final transcript, one automatic normal request, and product results.
2. Say `Show me three more.` and confirm automatic submission and unseen results.
3. Start and cancel before completion; verify no message/request.
4. Deny microphone access and verify the friendly fallback.
5. Click a speaker, confirm audible output, then stop and switch responses.
6. Repeat text, image, mixed, history and voice interactions on the final HTTPS URL.

**Real human-microphone recognition: not verified. Audible synthesis: not verified.**
No hardware success or accuracy is claimed from browser state or mocked events.
Some implementations use an online speech service; offline operation and identical
quality/voice availability across browsers are not guaranteed. HTTPS deployment
validation, language selection, Mandarin/Cantonese, continuous voice chat, and
recording uploads are outside this implementation.

API references: [SpeechRecognition final results](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognitionResult/isFinal),
[recognition end](https://developer.mozilla.org/en-US/docs/Web/API/SpeechRecognition/end_event),
and [synthesis cancellation](https://developer.mozilla.org/en-US/docs/Web/API/SpeechSynthesis/cancel).


## Voice Conversation Mode enhancement (2026-10-30)

Changes: `index.html`, `styles.css`, `app.js`, `voice.js`, `voice.test.js`,
`voice-app.test.js`, `README.md`, and this validation document. This section
supersedes the original manual-only behavior and test counts above.

The compact Voice Mode toggle defaults Off on page load. Unsupported synthesis
disables the toggle with an explanatory title; speech input and text chat remain
usable. The mode is session-only, including across chat switches; refreshing
returns it to Off. It is never serialized into localStorage or sent to the API.

Recognition still calls the original `submitMessage()`; an optional local-only
voice-origin argument is passed into `loadReply()`. Its in-memory job captures
whether Voice Mode was enabled at submission and the current speech revision.
After successful response processing, saving and rendering, the job may call the
existing playback controller only if it is still current, un-aborted, in the active
chat, the latest message, and Voice Mode remains enabled with the same revision.
Errors, ordinary typed messages, Retry, history rendering and an OFF→ON cycle
cannot acquire/revive automatic playback eligibility. Rendering itself never
starts playback. A successful empty-result reply can still be spoken.

The playback controller exposes `play()` alongside the existing manual `toggle()`;
both share the same utterance lifecycle, content sanitizer and stale-event guards.
No second TTS implementation is introduced. During any pending/active utterance,
the microphone is disabled and the recognition controller independently rejects
activation. Playback end, error or stop updates the speaker controls and restores
microphone availability without starting recognition. Turning the mode Off stops
current playback (including manual playback) and cancels recognition. Beginning a
new draft or selecting attachments invalidates delayed auto-speech as well.

Automatic speech failure leaves the rendered text/products in place and shows the
existing friendly speech error. It does not retry retrieval or resubmit text.
Some browsers may reject speech started after an asynchronous response under their
playback policy; the manual speaker button is the fallback. Final HTTPS/browser
and real audio hardware validation remain required.

### Current automated results

Frontend: **94 passed, zero failures**. Backend: **138 passed, zero failures**.
Total: **232 passed**. Commands are the same as above. Twelve added application
integration subtests cover default Off, toggles, historical renders, exact single
auto-play after voice reply, microphone blocking, completion without re-listening,
second voice turn, typed-message exclusion, mode-Off stop, manual fallback,
OFF→ON invalidation, new-draft suppression, failed API response, stale response
following chat switch, speech error without resubmission, active speaker stop,
and unsupported synthesis. The actual `app.js` is exercised with mock speech and
HTTP APIs. Earlier manual-only regression tests also continue passing. Backend
source/SKILL.md hashes match the pre-enhancement baseline.

### Actual browser checks for this enhancement

At http://127.0.0.1:8000/ in the available in-app browser:

- Reload restored existing five-result and three-result turns. Voice Mode showed
  Off; history did not automatically speak.
- Clicking the toggle changed its accessible pressed state to On; it did not
  start playback of existing responses.
- Clicking an existing speaker changed it to Stop reading response and disabled
  the microphone with a clear explanation.
- Turning Voice Mode Off restored the speaker and microphone to idle/available.
- At 375px width, the mode toggle, microphone and Send button remained inside the
  composer with no horizontal document overflow; the viewport was reset afterward.

These are actual UI/playback-request state checks, not proof of audible output.
The full two-turn auto-speech sequence was exercised in application tests with
mocked recognition, HTTP and synthesis events. It was **not** validated by a human
speaking into a real microphone, and synthesized audio was **not** audibly
verified. No such hardware success is claimed. Existing real live retrieval from
the earlier task is recorded above; this enhancement does not repeat or alter it.

### Human demonstration sequence

1. Open the local app (or final HTTPS deployment) in the demonstration browser.
2. Enable Voice Mode, click microphone, say “Show me five black T-shirts.” and stop.
3. Confirm one automatic submission, normal product rendering, and audible reply.
4. Confirm the microphone is unavailable while the reply is spoken and becomes
   available afterward without listening automatically.
5. Click microphone and say “Show me three more.” Confirm unseen results and a
   second audible reply.
6. Stop speech using its speaker button and by turning Voice Mode Off. Try an
   ordinary typed request with mode On: its reply must remain silent until clicked.
