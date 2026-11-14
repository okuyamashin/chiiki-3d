"""Compile scripts/tours/<code>.scenes.json for the terrain viewer.

Existing audio/NN.mp3 files set scene duration to narration + 1.2s lead + 0.9s tail.
Camera, caption and card times scale together. Without audio, retain draft timings.
Run again after generating or replacing narration; --require-audio rejects missing files.
"""
import argparse
import copy
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def retime(scene, duration):
    scene = copy.deepcopy(scene)
    ratio = duration / scene['duration']
    for key in ('camera', 'captions', 'cards'):
        for item in scene[key]:
            for field in ('t', 't0', 't1'):
                if field in item:
                    item[field] = round(item[field] * ratio)
    scene['duration'] = duration
    return scene


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('code')
    parser.add_argument('--require-audio', action='store_true')
    args = parser.parse_args()
    tour = json.loads((ROOT / 'scripts' / 'tours' / f'{args.code}.scenes.json').read_text())
    out = ROOT / 'output' / '3d'
    timeline, offset = [], 0
    for n, scene in enumerate(tour['steps'], 1):
        audio = out / 'audio' / args.code / f'{n:02d}.mp3'
        if args.require_audio and not audio.exists():
            parser.error(f'missing narration: {audio}')
        if audio.exists():
            seconds = float(subprocess.check_output([
                'ffprobe', '-v', 'error', '-show_entries', 'format=duration',
                '-of', 'csv=p=0', str(audio)], text=True))
            if seconds <= 0:
                parser.error(f'invalid audio duration: {audio}')
            scene = retime(scene, 1200 + round(seconds * 1000) + 900)
            scene['audio'] = audio.relative_to(out).as_posix()
            scene['timing'] = 'audio'
        else:
            scene['timing'] = 'draft'
        tour['steps'][n - 1] = scene
        timeline.append(f'{offset / 1000:7.2f}s  {scene["duration"] / 1000:6.2f}s  {scene["timing"]:5}  {n:02d} {scene["title"]}')
        offset += scene['duration']
    tour['duration'] = offset
    out.mkdir(parents=True, exist_ok=True)
    (out / f'tour_{args.code}.json').write_text(json.dumps(tour, ensure_ascii=False, indent=2) + '\n')
    (out / f'tour_{args.code}.timeline.txt').write_text('開始      長さ     時間根拠  場面\n' + '\n'.join(timeline) + '\n')
    print('\n'.join(timeline))
    print(f'Total: {offset / 1000:.2f}s (draft timings remain until narration is available)')


if __name__ == '__main__':
    main()
