// Render the viewer's intro (all of Japan -> the city) frame by frame and encode it as MP4.
//
// The page is opened with ?intro=1&render=1, which exposes window.introRender: setup() returns the length in ms,
// at(ms) draws that moment, loaded() tells whether every tile in view has arrived. Each frame waits for the
// tiles, so the video is smooth however slow the network or GPU is.
//
// Needs: the viewer served at --url (default http://localhost:8791/terrain.html), Google Chrome, ffmpeg.
// Run:   node scripts/render_intro.mjs [--code 01227] [--fps 30] [--size 1920x1080] [--ui 1.5] [--url ...]
//        --ui scales the page (CSS pixels = size / ui), as in render_tour.mjs, so the two cut together.
// Out:   output/video/intro_<code>.mp4  (frames in output/video/frames_<code>/)

import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import { mkdirSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const arg = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : d; };
const code = arg('code', '01227'), fps = +arg('fps', 30), ui = +arg('ui', 1.5), [W, H] = arg('size', '1920x1080').split('x').map(Number);
const url = `${arg('url', 'http://localhost:8791/terrain.html')}?code=${code}&intro=1&render=1`;
const outDir = join(ROOT, 'output', 'video'), frames = join(outDir, `frames_${code}`);
rmSync(frames, { recursive: true, force: true }); mkdirSync(frames, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--enable-gpu', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: Math.round(W / ui), height: Math.round(H / ui) }, deviceScaleFactor: ui });
page.on('pageerror', e => console.error('page error:', e.message));
await page.goto(url);
await page.waitForFunction(() => window.introRender && window.introRender.ready, null, { timeout: 120000 });
const total = await page.evaluate(() => window.introRender.setup());
const n = Math.ceil(total / 1000 * fps) + 1;
console.log(`${url}\n${n} frames, ${(total / 1000).toFixed(1)} s at ${fps} fps, ${W}x${H}`);

const t0 = Date.now();
for (let i = 0; i < n; i++) {
  await page.evaluate(ms => window.introRender.at(ms), Math.min(total, i * 1000 / fps));
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));  // let deck take the new layers
  // wait for the tiles of this view, then for two drawn frames
  await page.waitForFunction(() => window.introRender.loaded(), null, { timeout: 30000, polling: 50 }).catch(() => console.warn(`frame ${i}: tiles still loading`));
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
  await page.screenshot({ path: join(frames, `${String(i).padStart(5, '0')}.jpg`), type: 'jpeg', quality: 94 });
  if (i % 30 === 0) console.log(`frame ${i}/${n}  ${((Date.now() - t0) / 1000).toFixed(0)} s`);
}
await browser.close();

const mp4 = join(outDir, `intro_${code}.mp4`);
execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-framerate', String(fps), '-i', join(frames, '%05d.jpg'),
  '-c:v', 'libx264', '-preset', 'slow', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', mp4], { stdio: 'inherit' });
console.log(`-> ${mp4}`);
