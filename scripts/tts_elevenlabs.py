"""Narration audio for a tour (output/3d/tour_<code>.json) with ElevenLabs.

The text sent is the step's caption with the tour's "readings" applied (e.g. 字 -> あざ), the same text the
browser voice reads. Each file goes to output/3d/audio/<code>/<NN>.mp3 (NN = step number from 1) and the
step gets "audio": "audio/<code>/<NN>.mp3", which the viewer plays instead of the browser voice.

  --say 1,4          print the text for those steps (to paste into the ElevenLabs web app by hand)
  --attach           link mp3 files already in output/3d/audio/<code>/ (e.g. downloaded from the web app)
  --steps 1,4        generate those steps through the API (default: step 1 only, for a trial)
  --steps all        generate every step
  --voices           list the voices of the account

API use needs ELEVENLABS_API_KEY in the environment or in .env at the project root; the voice comes from
--voice or ELEVENLABS_VOICE_ID (environment or .env).
Run: .venv/bin/python -I scripts/tts_elevenlabs.py [--code 01227] ...
"""

import argparse
import json
import os
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = "https://api.elevenlabs.io/v1"


def env_file() -> dict:
    """KEY=value lines from .env at the project root (kept out of the code and the chat)."""
    f = ROOT / ".env"
    if not f.exists():
        return {}
    pairs = (l.split("=", 1) for l in f.read_text().splitlines() if "=" in l and not l.lstrip().startswith("#"))
    return {k.strip(): v.strip().strip("'\"") for k, v in pairs}


def reading(text: str, readings: dict) -> str:
    for k in sorted(readings, key=len, reverse=True):
        text = text.replace(k, readings[k])
    return text


def request(path: str, key: str, body: dict | None = None) -> bytes:
    req = urllib.request.Request(f"{API}{path}", headers={"xi-api-key": key, "Content-Type": "application/json"},
                                 data=None if body is None else json.dumps(body).encode(), method="GET" if body is None else "POST")
    with urllib.request.urlopen(req, timeout=180) as r:
        return r.read()


def pick(arg: str, n: int) -> list[int]:
    return list(range(1, n + 1)) if arg == "all" else [int(x) for x in arg.split(",")]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", default="01227")
    ap.add_argument("--steps", default="1")
    ap.add_argument("--say")
    ap.add_argument("--attach", action="store_true")
    ap.add_argument("--voices", action="store_true")
    ap.add_argument("--voice", default=os.environ.get("ELEVENLABS_VOICE_ID"))
    ap.add_argument("--model", default="eleven_multilingual_v2")
    a = ap.parse_args()

    tour_path = ROOT / "output" / "3d" / f"tour_{a.code}.json"
    tour = json.loads(tour_path.read_text())
    steps, rd = tour["steps"], tour.get("readings", {})
    adir = ROOT / "output" / "3d" / "audio" / a.code

    if a.say:
        for n in pick(a.say, len(steps)):
            print(f"--- {n:02d} {steps[n - 1]['title']}\n{reading(steps[n - 1]['text'], rd)}\n")
        return

    if a.attach:
        for n, st in enumerate(steps, 1):
            f = adir / f"{n:02d}.mp3"
            if f.exists():
                st["audio"] = f"audio/{a.code}/{f.name}"
                print(f"linked {n:02d} {st['title']}")
        tour_path.write_text(json.dumps(tour, ensure_ascii=False, indent=1))
        return

    key = os.environ.get("ELEVENLABS_API_KEY") or env_file().get("ELEVENLABS_API_KEY")
    a.voice = a.voice or env_file().get("ELEVENLABS_VOICE_ID")
    if not key:
        raise SystemExit("set ELEVENLABS_API_KEY in the environment or in .env at the project root")
    if a.voices:
        for v in json.loads(request("/voices", key))["voices"]:
            print(v["voice_id"], v["name"], v.get("labels", {}))
        return
    if not a.voice:
        raise SystemExit("pass --voice <voice_id> or set ELEVENLABS_VOICE_ID (see --voices)")

    adir.mkdir(parents=True, exist_ok=True)
    for n in pick(a.steps, len(steps)):
        st = steps[n - 1]
        body = {"text": reading(st["text"], rd), "model_id": a.model,
                "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}}
        mp3 = request(f"/text-to-speech/{a.voice}?output_format=mp3_44100_128", key, body)
        f = adir / f"{n:02d}.mp3"
        f.write_bytes(mp3)
        st["audio"] = f"audio/{a.code}/{f.name}"
        print(f"{n:02d} {st['title']}: {len(body['text'])} chars -> {f.relative_to(ROOT)} ({len(mp3) / 1e3:.0f} kB)")
    tour_path.write_text(json.dumps(tour, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
