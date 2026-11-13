"""Japanese subtitles (SRT) and YouTube chapters for output/video/movie_<code>.mp4.

Timing follows the video exactly: the opening (intro video length), then for each tour step
camera 1.2 s -> narration (its mp3 length) -> 0.9 s gap, as in render_tour.mjs. Inside one narration
each sentence gets time in proportion to its length, so cues can drift by a fraction of a second.
Captions use the written text (kanji), not the readings sent to the voice.

Run:  .venv/bin/python -I scripts/make_subtitles.py [code]      (default 01227)
Out:  output/video/movie_<code>.ja.srt
      output/video/movie_<code>.en.srt   (if output/3d/tour_<code>.en.json gives one English line per sentence)
      output/video/chapters_<code>.txt    (YouTube chapter lines, 0:00 first; .en.txt with English titles)
"""

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SAY, GAP = 1.2, 0.9          # same as render_tour.mjs
MAX_LINE = 30                # characters per subtitle line before wrapping


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(out)


def stamp(t: float) -> str:
    ms = round(t * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def wrap_en(sentence: str, width: int = 50) -> str:
    """Break a long English sentence into two lines at the space nearest the middle."""
    if len(sentence) <= width:
        return sentence
    mid = len(sentence) / 2
    k = min((i for i, ch in enumerate(sentence) if ch == " "), key=lambda i: abs(i - mid))
    return sentence[:k] + "\n" + sentence[k + 1:]


def wrap(sentence: str) -> str:
    """Break a long sentence into two lines at the 、 nearest the middle."""
    if len(sentence) <= MAX_LINE:
        return sentence
    cuts = [m.end() for m in re.finditer("、", sentence)]
    if not cuts:
        return sentence
    mid = len(sentence) / 2
    k = min(cuts, key=lambda c: abs(c - mid))
    return sentence[:k] + "\n" + sentence[k:]


def main() -> None:
    code = sys.argv[1] if len(sys.argv) > 1 else "01227"
    video = ROOT / "output" / "video"
    tour = json.loads((ROOT / "output" / "3d" / f"tour_{code}.json").read_text())
    intro = duration(video / f"intro_{code}.mp4")

    en_path = ROOT / "output" / "3d" / f"tour_{code}.en.json"
    en = json.loads(en_path.read_text())["steps"] if en_path.exists() else None
    cues, chapters, cues_en, chapters_en = [], [(0.0, "オープニング")], [], [(0.0, "Opening")]
    # the opening has only music and its own on-screen caption, so subtitles start with the tour
    t = intro
    for n, st in enumerate(tour["steps"]):
        chapters.append((t, st["title"]))
        d = duration(ROOT / "output" / "3d" / st["audio"])
        a = t + SAY
        parts = re.findall(r"[^。]+。?", st["text"])
        total = sum(len(p) for p in parts)
        if en:
            chapters_en.append((t, en[n]["title"]))
            assert len(en[n]["sentences"]) == len(parts), f"step {n + 1}: {len(parts)} Japanese sentences"
        start = a
        for k, p in enumerate(parts):
            end = start + d * len(p) / total
            cues.append((start, end, wrap(p.strip())))
            if en:
                cues_en.append((start, end, wrap_en(en[n]["sentences"][k])))
            start = end
        t = a + d + GAP

    srt = lambda cs: "\n".join(f"{i}\n{stamp(s)} --> {stamp(e)}\n{text}\n" for i, (s, e, text) in enumerate(cs, 1))
    chap = lambda cs: "\n".join(f"{int(s // 60)}:{int(s % 60):02d} {title}" for s, title in cs) + "\n"
    (video / f"movie_{code}.ja.srt").write_text(srt(cues), encoding="utf-8")
    ch = chap(chapters)
    (video / f"chapters_{code}.txt").write_text(ch, encoding="utf-8")
    if en:
        (video / f"movie_{code}.en.srt").write_text(srt(cues_en), encoding="utf-8")
        (video / f"chapters_{code}.en.txt").write_text(chap(chapters_en), encoding="utf-8")
    print(f"{len(cues)} cues -> {video / f'movie_{code}.ja.srt'}\n{ch}")


if __name__ == "__main__":
    main()
