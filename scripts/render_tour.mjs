// Render the narrated tour frame by frame and encode it with its narration as MP4.
//
// The page (?render=1) exposes window.tourRender: setup(durations) lays out the timeline (camera flies 2.2 s from
// each step start, narration at +1.2 s, next step 0.9 s after it ends) and at(ms) draws any moment of it.
// The narration mp3s named in tour_<code>.json are placed on the same timeline with ffmpeg.
//
// Needs: the viewer served at --url, Google Chrome, ffmpeg/ffprobe.
// Run:   node scripts/render_tour.mjs [--code 01227] [--fps 30] [--size 1920x1080] [--ui 1.5] [--url ...]
//        --ui scales the page (CSS pixels = size / ui) so captions and labels read well in the video.
//        --recorded output/video/rec_<code>_h264.mp4 mixes narration onto a real-time recording instead.
// Out:   output/video/tour_<code>.mp4  (frames in output/video/frames_tour_<code>/)

import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import { mkdirSync, readFileSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const arg = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : d; };
const code = arg('code', '01227'), fps = +arg('fps', 30), ui = +arg('ui', 1.5);
const [W, H] = arg('size', '1920x1080').split('x').map(Number);
const url = `${arg('url', 'http://localhost:8791/terrain.html')}?code=${code}&render=1`;
const out = join(ROOT, 'output', 'video'), frames = join(out, `frames_tour_${code}`);
const tour = JSON.parse(readFileSync(join(ROOT, 'output', '3d', `tour_${code}.json`), 'utf8'));
const files = tour.steps.map(s => join(ROOT, 'output', '3d', s.audio));
const durs = files.map(f => +execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f]).toString());
const recorded = arg('recorded', null);
let offset = 0;
const audioAt = durs.map(d => { const at = offset + 1200; offset += 1200 + d * 1000 + 900; return at; });
const total = offset - 900 + 2500;
if (recorded) {
  const seconds = +execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', recorded]).toString();
  if (Math.abs(seconds - total / 1000) > .1) throw Error('録画と音声の時間が一致しません。台本を再コンパイルして録り直してください');
} else {
rmSync(frames, { recursive: true, force: true }); mkdirSync(frames, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--enable-gpu', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: Math.round(W / ui), height: Math.round(H / ui) }, deviceScaleFactor: ui });
page.on('pageerror', e => console.error('page error:', e.message));
await page.goto(url);
await page.waitForFunction(() => window.introRender && window.introRender.ready, null, { timeout: 120000 });
await page.evaluate(d => window.tourRender.setup(d), durs);
const n = Math.ceil(total / 1000 * fps) + 1;
console.log(`${n} frames, ${(total / 1000).toFixed(1)} s, ${tour.steps.length} steps`);

const raf = () => page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
const t0 = Date.now();
for (let i = 0; i < n; i++) {
  await page.evaluate(ms => window.tourRender.at(ms), i * 1000 / fps);
  await raf();
  await page.waitForFunction(() => window.tourRender.loaded(), null, { timeout: 30000, polling: 50 }).catch(() => console.warn(`frame ${i}: still loading`));
  await raf();
  await page.screenshot({ path: join(frames, `${String(i).padStart(5, '0')}.jpg`), type: 'jpeg', quality: 92 });
  if (i % 300 === 0) console.log(`frame ${i}/${n}  ${((Date.now() - t0) / 1000).toFixed(0)} s`);
}
await browser.close();
}

// narration: each step's mp3 delayed to its start, mixed, padded to the video length
const inputs = files.flatMap(f => ['-i', f]);
const delays = audioAt.map((ms, k) => `[${k}:a]aresample=48000,aformat=channel_layouts=stereo,adelay=${Math.round(ms)}|${Math.round(ms)}[a${k}]`);
const mix = `${delays.join(';')};${audioAt.map((_, k) => `[a${k}]`).join('')}amix=inputs=${files.length}:normalize=0,apad,atrim=0:${(total / 1000).toFixed(3)}[aout]`;
const mp4 = join(out, `tour_${code}.mp4`);
const videoInput = recorded ? ['-i', recorded] : ['-framerate', String(fps), '-i', join(frames, '%05d.jpg')];
const videoCodec = recorded ? ['-c:v', 'copy'] : ['-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p'];
execFileSync('ffmpeg', ['-y', '-loglevel', 'error', ...videoInput, ...inputs,
  '-filter_complex', mix.replace(/\[(\d+):a\]/g, (_, k) => `[${+k + 1}:a]`), '-map', '0:v', '-map', '[aout]',
  ...videoCodec, '-c:a', 'aac', '-b:a', '192k', '-shortest',
  '-movflags', '+faststart', mp4], { stdio: 'inherit' });
console.log(`-> ${mp4}`);
