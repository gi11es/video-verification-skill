# Video Verification Skill

Record real browser tests and produce a narrated verification video with captions, evidence, and a shareable report.

## Dependencies

- **Python 3.10+** — helpers use only the standard library.
- **Playwright + a supported browser** — application recording and verification.
- **FFmpeg + ffprobe** with H264/AAC support — editing and export.
- **OpenRouter account + API key** — paid narration using `elevenlabs/eleven-multilingual-v2`, voice `george`. Supply `OPENROUTER_API_KEY` or `--key-file`.
- **cloudflared** — optional temporary public hosting.
- **Pillow** — optional title cards and annotations.
- Access to your running app; tracker and observability integrations when needed.

Install these separately. No credentials are bundled.

## Install and use

Download the [latest ZIP](../../releases/latest), then copy the entire `video/` directory into your agent's skills directory. Invoke `$video` or `/video`, or point your agent at [video/SKILL.md](video/SKILL.md).

Specify the target build and authorize any paid narration or public publication.

See the [production guide](video/references/production.md) for capture, editing, helper commands, and hosting. Start chapter manifests from [examples/scenes.json](examples/scenes.json).

## Test helpers

```sh
python3 -m unittest discover -s tests -v
```
