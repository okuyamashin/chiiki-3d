#!/bin/sh
# Copy the 3D viewer and one area's data into docs/ (GitHub Pages serves docs/ on main).
# Usage: sh scripts/publish_pages.sh [code ...]   (default 01227 = 歌志内市)
set -e
cd "$(dirname "$0")/.."
[ $# -gt 0 ] || set -- 01227
mkdir -p docs
cp output/3d/terrain.html docs/index.html
touch docs/.nojekyll
for c in "$@"; do
  cp output/3d/terrain_$c.json output/3d/terrain_$c.bin output/3d/terrain_$c.mask.bin output/3d/terrain_$c.aza.bin docs/
  [ -f output/3d/tour_$c.json ] && cp output/3d/tour_$c.json docs/
  [ -f output/3d/tour_$c.en.json ] && cp output/3d/tour_$c.en.json docs/   # English subtitles source
  if [ -d output/3d/audio/$c ]; then
    mkdir -p docs/audio/$c
    cp output/3d/audio/$c/[0-9][0-9].mp3 docs/audio/$c/   # narration only, not the voice trials
  fi
done
du -sh docs
