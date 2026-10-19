# Video Verification Skill

An agent skill for recording real browser verification, explaining a change's root cause, and delivering an edited video with narration, captions, coverage, and follow-up findings.

The workflow covers the affected behavior, checks persistence after reload, distinguishes browser footage from backend evidence, and restarts verification after an in-scope fix. Backend changes can be explained with clearly labelled animated diagrams. A reviewed public export can be shared through a temporary Cloudflare tunnel.

## What's included

```text
video/
  SKILL.md                  Agent workflow and evidence requirements
  references/production.md  Capture, editing, narration and publishing guide
  scripts/narrate.py        OpenRouter narration with cached audio and receipts
  scripts/serve.py          Loopback export server with HTTP byte ranges
examples/scenes.json        Editable chapter manifest
tests/test_helpers.py      Offline checks for the helpers
```

The Python helpers use the standard library. They do not perform application tests or edit a finished video automatically; the agent drives the workflow using the application and media tools.

## Requirements

- Python 3.10 or newer for the helpers.
- Playwright with a supported browser, available through your agent or project tooling.
- A working application environment and access to the target build.
- FFmpeg and ffprobe with H264 video and AAC audio support for editing and export.
- cloudflared if you want temporary public hosting.
- Your own OpenRouter account and API key for paid narration. The default model is `elevenlabs/eleven-multilingual-v2`, voice `george`.
- Your project's tracker and observability integrations when the verification needs them.

Pillow is optional for title cards and editorial annotations. No application credentials, private configuration, or personal pre-approvals are bundled. Installation does not install these external tools.

## Install

Download and unpack the release ZIP, or clone this repository. Copy the **entire `video` directory**, including `references` and `scripts`, to your agent's skill directory. Keep your existing skill backed up if one already uses that name.

For Codex, the usual destination is `~/.codex/skills/video/`. For Claude Code, use `~/.claude/skills/video/` or a project's `.claude/skills/video/`. Follow your agent's skill-discovery rules if it uses a different layout. You can also point an agent directly at `video/SKILL.md` without installing it.

Request the workflow with `$video` or `/video`, as supported by your agent. For example:

> Use the video skill to verify this settings fix on my local test app. Check save and reload behavior, explain the confirmed root cause, and produce a narrated video and coverage report. You may use my configured speech account and publish the reviewed export through a temporary tunnel.

Specify the target build, permitted fixtures, and whether paid narration, public publication, tracker writes, fixes, or staging deployment are authorized. The shared skill does not inherit someone else's approvals. It does not authorize production changes or merging.

## Generate narration

Copy `examples/scenes.json` into a private run directory and replace its example script and clip metadata with your verified facts. Create output outside this repository or under an ignored `artifacts/` directory.

Provide your key using your existing secret manager or the `OPENROUTER_API_KEY` environment variable. Alternatively, pass the path to an existing private credential file:

```sh
python3 video/scripts/narrate.py /path/to/scenes.json \
  --out /path/to/private-run/audio \
  --key-file /path/to/private/openrouter-key
```

Use mode `0700` for private directories and `0600` for key files. Never paste a key into source, a manifest, a report, or a shell command that may be recorded. The helper reads the environment first, then the explicitly supplied key file; there is no machine-specific default credential path.

The helper writes one MP3 and one JSON receipt per chapter. Unchanged script/model/voice and matching audio hashes reuse the existing audio. Receipts include the narration text, model, voice, hashes, and generation ID, so review them before sharing. Text is sent to the speech provider; only send content authorized for that destination. Missing credentials or a failed request stop generation rather than substituting another voice.

## Publish a reviewed export

Follow [the production guide](video/references/production.md) for recording, editing, captions, diagrams, and validation. Put only reviewed HTML, MP4, captions, scripts, and sanitized evidence in a dedicated public directory. Keep authentication state, raw recordings, logs, and secrets elsewhere.

```sh
python3 video/scripts/serve.py /path/to/reviewed-public-export --port 8837
```

In another terminal:

```sh
cloudflared tunnel --url http://127.0.0.1:8837 --no-autoupdate
```

Use the actual public URL reported by cloudflared. Check playback, seeking, captions, downloads, mobile layout, and HTTP206 byte ranges through that hostname. The helper disables directory listings, dotfiles, and file symlinks; it serves all other files in the selected directory, so it is not a substitute for reviewing the export.

Quick Tunnels remain available only while the machine and both processes stay online. They are temporary hosting. Narration and hosting commands do not certify that a change works; preserve the underlying assertions, build identity, coverage, and limits.

## Check the helpers

```sh
python3 -m unittest discover -s tests -v
```

These tests use a temporary directory, a loopback HTTP server, and a mocked speech endpoint. They do not call the speech provider, spend money, or read your configured credentials.
