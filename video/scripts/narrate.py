#!/usr/bin/env python3
"""Generate cached chapter narration through OpenRouter; never emit secrets."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

MODEL = "elevenlabs/eleven-multilingual-v2"
VOICE = "george"
ENDPOINT = "https://openrouter.ai/api/v1/audio/speech"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("scenes", type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--key-file", type=Path, help="Optional private file containing the OpenRouter API key")
    args = parser.parse_args()
    try:
        scenes = json.loads(args.scenes.read_text())
        if not isinstance(scenes, list) or not scenes:
            raise ValueError("Expected a nonempty list of chapters")
        ids = set()
        for scene in scenes:
            sid = scene.get("id", "")
            text = scene.get("narration", "")
            if not isinstance(sid, str) or not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", sid) or sid in ids:
                raise ValueError("Chapter IDs must be unique, safe filenames, at most 64 characters")
            if not isinstance(text, str) or not text.strip() or len(text) > 10000:
                raise ValueError("Each narration must contain 1–10000 characters")
            ids.add(sid)
    except (OSError, ValueError, TypeError, AttributeError):
        print("Invalid chapter manifest; use unique safe IDs and 1–10000 characters per narration", file=sys.stderr)
        return 2

    args.out.mkdir(parents=True, exist_ok=True)
    key = None
    for scene in scenes:
        sid = scene["id"]
        text = scene["narration"]
        digest = hashlib.sha256(json.dumps([MODEL, VOICE, text], ensure_ascii=False).encode()).hexdigest()
        audio = args.out / (sid + ".mp3")
        receipt = args.out / (sid + ".json")
        try:
            old = json.loads(receipt.read_text()) if receipt.exists() else {}
            if audio.exists() and old.get("request_sha256") == digest and old.get("audio_sha256") == hashlib.sha256(audio.read_bytes()).hexdigest():
                print(sid + ": cached", flush=True)
                continue
        except (OSError, ValueError):
            pass
        if key is None:
            key = os.environ.get("OPENROUTER_API_KEY", "").strip()
            if not key:
                if args.key_file is None:
                    print("OpenRouter key unavailable; set OPENROUTER_API_KEY or supply --key-file", file=sys.stderr)
                    return 2
                try:
                    key = args.key_file.read_text().strip()
                except OSError:
                    print("OpenRouter key unavailable; check the private cache or configured environment", file=sys.stderr)
                    return 2
            if not key:
                print("OpenRouter key is empty", file=sys.stderr)
                return 2
        request = urllib.request.Request(
            ENDPOINT,
            data=json.dumps({"model": MODEL, "voice": VOICE, "response_format": "mp3", "input": text}).encode(),
            headers={"Authorization": "Bearer " + key, "Content-Type": "application/json", "X-Title": "Narrated video verification"},
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                mime = response.headers.get("Content-Type", "")
                generation = response.headers.get("X-Generation-Id")
                if not mime.startswith("audio/"):
                    print(sid + ": speech API returned a non-audio response", file=sys.stderr)
                    return 1
                body = response.read()
            if len(body) < 128:
                print(sid + ": speech API returned empty/truncated audio", file=sys.stderr)
                return 1
        except urllib.error.HTTPError as error:
            print(sid + ": OpenRouter HTTP " + str(error.code) + "; no response body logged and no model substituted", file=sys.stderr)
            return 1
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            print(sid + ": speech request failed; credentials and response body withheld", file=sys.stderr)
            return 1
        audio.write_bytes(body)
        receipt.write_text(json.dumps({
            "provider": "OpenRouter", "endpoint": ENDPOINT, "model": MODEL, "voice": VOICE,
            "format": "mp3", "generation_id": generation, "request_sha256": digest,
            "audio_sha256": hashlib.sha256(body).hexdigest(), "text": text,
        }, indent=2))
        print(sid + ": generated", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
