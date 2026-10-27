# Capture, narration, editing and delivery

Helpers handle repeatable mechanics; they do not perform or certify the application tests.

## Capture and files

Keep a private run directory outside the repository, one attempt/build per subdirectory. Keep authentication elsewhere. Use a separate `public/` directory for reviewed exports only; never tunnel the private run directory. Keep the access key file (`access.key`, mode 600) in the run directory, outside `public/`. A useful layout is `attempt-02/{raw/,screenshots/,timeline.json,coverage.json,runtime-proof.json}`, plus `edit/`, `audio/`, `scenes.json` and `public/`.

Playwright pattern (adapt login/imports to the repository):

```js
// Authenticate without recordVideo; never film login.
const storageState = await authenticatedContext.storageState()
const startedAt = Date.now()
const context = await browser.newContext({
  storageState,
  viewport: { width: 1440, height: 1000 },
  recordVideo: { dir: runDir + '/raw', size: { width: 1440, height: 1000 } },
})
const page = await context.newPage()
const video = page.video()
// Per scenario: raw offset, UTC, exact assertions/observed facts, build,
// fixture IDs, outcome and screenshot paths. Collect GraphQL response.errors.
await context.close() // finalizes recording
const rawFile = await video.path()
```

Save assertion facts: the actual selector/property, mutation count, retry event ID/phase or backend resolution. An ARIA snapshot may omit a generic span's accessible label; save the asserted DOM property when it matters. Don't collect secret-bearing HTTP bodies. Navigation ERR_ABORTED and favicon failures are not automatically product regressions.

## Speech helper

`python3 scripts/narrate.py <scenes.json> --out <audio-dir>` calls OpenRouter per chapter and writes MP3 + receipt JSON. Cache identity includes script/model/voice. It reads `OPENROUTER_API_KEY` or a private key file explicitly supplied with `--key-file` directly, without printing credentials or response bodies. It fails instead of changing voice.

```json
[
  {
    "id": "saved-settings",
    "title": "Saved settings survive reload",
    "narration": "After a full reload, the saved setting still displays the selected value.",
    "clips": [{"file": "attempt-02/raw/session.webm", "start": 42.5, "end": 51.2, "revision": "final-build-sha"}],
    "note": "Real staging footage; reload verified"
  }
]
```

Paths are relative to the manifest. Audio generation needs only `id` and `narration`; editing fields are for the editor/agent. Use short safe IDs. Receipts contain generation IDs, script hash/text and model/voice, never keys. Model `elevenlabs/eleven-multilingual-v2`, voice `george`, endpoint `https://openrouter.ai/api/v1/audio/speech`, raw MP3 response. Split text over 10,000 characters into natural chapters. Check current API docs after a contract error; don't silently substitute providers/models.

## Edit actual clips

Use FFmpeg and existing project tooling. Python/Pillow can create title/annotation graphics; browser captures prove the app. Label summaries separately. Some local FFmpeg builds omit drawtext/subtitles filters: PNG overlays, WebVTT captions and embedded mov_text tracks are alternatives.

1. Cut raw ranges and concatenate action → outcome → reload. Exclude idle navigation and unrelated lists. Preserve aspect ratio with padding. Keep an edit list with source paths, offsets, build and transforms.
2. Match audio to chapters. Label a frozen last frame `Frame held for narration`; don't announce an outcome before it appears. Default to real-time actions; disclose shortened waits/speed changes.
3. Prefer full view → cut to a labelled close-up → return to full view. Do not overlay an enlarged copy on its visible source: a second card or panel can look like nested UI. If two views are necessary, put them in separate, bordered regions labelled `Full view` and `Detail`, with a clear gap. Use a close-up only when it improves readability.
4. Optional animated zooms must crop the real source while its time advances. Move briefly to a clearly larger, readable scale, hold, then return to context. Do not spread a tiny scale change across the narration. Watch the transition at normal speed and replace it with a cut if it feels slow or adds no useful information. A zoomed screenshot is a labelled still. Record keyframes/crops in the edit list. Never use generative frames, generative upscaling or interpolated UI to improve apparent results.
5. Use a brief circle, outline, arrow or highlight when it helps locate a control, changed value or result. Identify these cues as editorial annotations in a visible legend or label. Keep strokes outside the target text and controls; use transparent fills that preserve evidence. Keep a cue aligned with its target during movement and remove it once the viewer can locate the target. Do not decorate every click or use a cue to suggest an unproved state.
6. Inspect each rendered transition, annotation, action and failure at actual output size and normal playback speed. Check that duplicated views cannot be mistaken for app structure, close-ups improve readability, and cues and captions leave the tested control/error visible. Add an exact script, SRT/WebVTT, and chapters. Disclose estimated timing when captions aren't speech-aligned.

## Summary and diagram chapters

Every video starts with a `summary` chapter (bug symptom → root cause → fix), followed by `diagram-*` chapters when backend behavior is not visible in the UI. Put them first in `scenes.json`, with `"kind": "summary"` or `"kind": "diagram"` and a `sources` list (file paths with line ranges, PR, trace/log IDs) that supports each step shown.

Summary chapter: a clean title card or a simple text-and-icon slide (symptom, root cause, fix, one line each), narrated. Include a brief introduction-history line following `SKILL.md`: when/how the bug was introduced if established, or what remains unknown. It may show one short real clip or screenshot of the symptom, labelled with its source.

Animated diagrams:

1. Write the diagram as a small, self-contained HTML/SVG (or CSS-animated) page in the private run directory. Use a sequence-diagram or state-flow layout: one lane per real actor (browser, web server, background worker, coordination service, database, deployment platform, external API), arrows for calls/messages, and state badges for the values that matter (lease holder, retry count, job state).
2. Animate step by step, timed to the narration: the failing path first, ending at the failure point (mark it in red with the actual error name), then a reset and the fixed path, with the changed step highlighted (for example in green) and labelled `Fix`. Hold each step long enough to read at normal speed. Keep text large enough for the delivered resolution.
3. Render with Playwright `recordVideo` at the video resolution (for example 1440×1000 or 1920×1080), or export frames and encode with FFmpeg. Do not use generative video or image models for diagrams; their output cannot be checked against the code.
4. Put a persistent corner label `Diagram — not app footage` on every frame, and use a visual style (background, fonts, colors) that is clearly different from the app UI.
5. Review each diagram against the code and the evidence before narration: every arrow and state must exist in the code path or in the observed trace. Record the mapping in the edit list.

Encode `-c:v libx264 -pix_fmt yuv420p -c:a aac -movflags +faststart`. Use two-pass `loudnorm=I=-16:TP=-1.5:LRA=11`, with measured values in pass two. Preserve video/subtitles/chapters during audio-only normalization. Check ffprobe (duration, dimensions, audio/codecs, chapters) and full decode: `ffmpeg -v error -i final.mp4 -map 0:v -map 0:a -f null -`. A successful encode isn't a browser playback test.

## Report

Put a short written summary (bug, root cause, fix) above or beside the player. Use `<video controls playsinline preload="metadata">`, MP4 source, WebVTT captions and chapter buttons. Include download links and a responsive gallery/coverage matrix. Put a visible findings table beside the player: finding, scope/status, **actual tracker URL and requesting-user assignee**, evidence/chapter, workaround. Include fixed in-scope bugs and retest build; list missing coverage separately. Avoid third-party assets/trackers.

Export only selected reviewed files: HTML, MP4, captions/script, selected screenshots and coverage/telemetry. Do not blur or redact footage or screenshots; the access key protects them. Raw footage is optional. Never publish cookie files, secrets, the access key file, raw logs, private scripts or the entire run directory. Use relative links inside the report so that they stay below `/<key>/`.

## Key-protected Cloudflare hosting

The bundled server serves files only below `/<key>/` and returns 404 for every other path. It refuses dotfiles, symlinks and directory listings, supports HTTP byte ranges, sends `Referrer-Policy: no-referrer` and `X-Robots-Tag: noindex`, and writes `<key>` instead of the key in request logs. Start it on a free loopback port, then a Quick Tunnel:

```sh
# Use persistent tool sessions or managed detached processes with private
# PID/log records. Substitute actual absolute paths; don't kill occupied ports.
python3 <skill-dir>/scripts/serve.py <public-dir> --port 8837 --key-file <run-dir>/access.key
cloudflared tunnel --url http://127.0.0.1:8837 --no-autoupdate
```

Read the actual `https://…trycloudflare.com` hostname from the cloudflared log and the key from the key file. The deliverable link is `https://<host>.trycloudflare.com/<key>/`. No Cloudflare login/account is required. Keep both processes running after the final reply and keep lifecycle files outside the export. If either exits, diagnose/restart and validate the new URL; the key file keeps the key, but a new tunnel gets a new hostname. Quick Tunnels have no uptime guarantee and depend on this machine/processes staying online; don't present permanent hosting. If an existing cloudflared config interferes, inspect the error and isolate the new tunnel rather than overwriting/renaming the user's config blindly.

Validate through the **keyed** public URL:

- `https://<host>/` and `https://<host>/<wrong-key>/` return 404.
- `https://<host>/<key>/` opens without login or challenge; no page errors.
- Browser playback succeeds: currentTime advances, videoWidth>0, readyState>=2, error===null.
- Seek to a later chapter and verify decoded frames/time advance.
- MP4 `Range: bytes=0-1023` returns HTTP206, correct Content-Range, length and MIME type.
- Captions, chapters and MP4/script downloads work.
- Phone viewport can operate the player and read findings without clipping.

Attach evidence/chapter links to filed tasks only if the user asked to share the key there, then read back assignments. Tracker/public-playback failure means incomplete delivery: say exactly what remains.

Primary references: [OpenRouter speech API](https://openrouter.ai/docs/guides/overview/multimodal/tts), [Cloudflare Quick Tunnels](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/), [Claude Code skills](https://code.claude.com/docs/en/skills).
