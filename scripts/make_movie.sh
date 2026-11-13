#!/bin/sh
# Join the opening (intro video + its soundtrack) and the narrated tour into one MP4.
# Run after scripts/render_intro.mjs, scripts/make_intro_audio.mjs and scripts/render_tour.mjs.
# Usage: sh scripts/make_movie.sh [code]   (default 01227) -> output/video/movie_<code>.mp4
set -e
cd "$(dirname "$0")/.."
c=${1:-01227}
v=output/video
d=$(ffprobe -v error -show_entries format=duration -of csv=p=0 $v/intro_$c.mp4)
ffmpeg -y -loglevel error -i $v/intro_$c.mp4 -i output/audio/intro.wav -i $v/tour_$c.mp4 -filter_complex "\
[1:a]aresample=48000,aformat=channel_layouts=stereo,atrim=0:$d,apad=whole_dur=$d[ia];\
[2:a]aresample=48000,aformat=channel_layouts=stereo[ta];\
[0:v][ia][2:v][ta]concat=n=2:v=1:a=1[v][a]" \
  -map "[v]" -map "[a]" -c:v libx264 -preset slow -crf 18 -pix_fmt yuv420p -c:a aac -b:a 192k \
  -movflags +faststart $v/movie_$c.mp4
ffprobe -v error -show_entries format=duration,size -of compact $v/movie_$c.mp4
