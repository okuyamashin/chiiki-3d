// Still images for the note article (articles/note_<code>.md): the two charts, the population map and a
// 2000 / 2020 comparison with age pyramids. Uses the viewer in render mode (no panel, no tour bar).
//
// Needs: the viewer served at --url, Google Chrome, ffmpeg.
// Run:   node scripts/render_note_images.mjs [--code 01227] [--url ...]
// Out:   output/note_<code>/01_longrun.png, 02_industry.png, 03_map2020.png, 04_compare.png

import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import { mkdirSync, rmSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const arg = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : d; };
const code = arg('code', '01227');
const url = `${arg('url', 'http://localhost:8791/terrain.html')}?code=${code}&render=1`;
const out = join(ROOT, 'output', `note_${code}`);
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({ channel: 'chrome', headless: true, args: ['--enable-gpu', '--ignore-gpu-blocklist'] });
const page = await browser.newPage({ viewport: { width: 1200, height: 675 }, deviceScaleFactor: 2 });  // 2400x1350
page.on('pageerror', e => console.error('page error:', e.message));
await page.goto(url);
await page.waitForFunction(() => window.introRender && window.introRender.ready, null, { timeout: 120000 });
await page.evaluate(() => { document.body.classList.add('render'); map.setProps({ controller: false }); });
const settle = async () => {
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
  await page.waitForFunction(() => window.tourRender.loaded(), null, { polling: 100, timeout: 60000 });
  await page.evaluate(() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r))));
};
// a scene: settings + camera (same keys as a tour step's "set" and "view"), optional big year label
const scene = (set, v, label) => page.evaluate(([set, v, label]) => {
  state.focus = null; applyState(set); setView(viewFor(v, []));
  let el = document.getElementById('noteLabel');
  if (!el) {
    el = document.createElement('div'); el.id = 'noteLabel';
    el.style.cssText = 'position:absolute;left:28px;top:20px;font-size:44px;font-weight:800;color:#fff;' +
      'text-shadow:0 2px 6px rgba(0,0,0,.8);pointer-events:none;letter-spacing:.04em';
    document.body.appendChild(el);
  }
  el.textContent = label || '';
}, [set, v, label]);

// charts: the chart card alone, at 3x so it stays sharp in the article
await page.setViewportSize({ width: 1200, height: 675 });
for (const [name, chart] of (code === '05327' ? [['02_industry', 'industry']] : [['01_longrun', 'longrun'], ['02_industry', 'industry']])) {
  await scene({ chart, year: 2020, popColor: true, pyr: false }, { at: 'target', zoom: 11.2, pitch: 60, bearing: -30 });
  await settle();
  await page.locator('#chart').screenshot({ path: join(out, `${name}.png`), scale: 'device' });
  console.log(`${name}.png`);
}

if (code === '05327') {
  await scene({ chart: '', year: 2020, popColor: false, pyr: false }, { at: [140.31,39.95], zoom: 10.25, pitch: 45, bearing: -15 }, '上小阿仁村の地形');
  await settle();
  await page.screenshot({ path: join(out, '01_terrain.png') });
}
// the map coloured by 2020 population, no chart
const MAPVIEW = code === '05327' ? { at: [140.31,40.052], zoom: 11.55, pitch: 45, bearing: -15 } : { at: 'target', zoom: 11.9, pitch: 55, bearing: -30, shift: [0, 0.004] };
await scene({ chart: '', year: 2020, popColor: true, pyr: false }, MAPVIEW);
await settle();
await page.screenshot({ path: join(out, '03_map2020.png') });
console.log('03_map2020.png');

// 2000 and 2020 with age pyramids, stacked
const CMP = code === '05327' ? { at: [140.31,40.052], zoom: 11.4, pitch: 45, bearing: -15 } : { at: 'target', zoom: 12.3, pitch: 45, bearing: -30, shift: [0, 0.012] };
for (const y of [2000, 2020]) {
  await scene({ chart: '', year: y, popColor: true, pyr: code !== '05327' }, CMP, `${y}年`);
  await settle();
  await page.screenshot({ path: join(out, `_cmp_${y}.png`) });
}
await browser.close();
execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', join(out, '_cmp_2000.png'), '-i', join(out, '_cmp_2020.png'),
  '-filter_complex', '[0][1]vstack', join(out, '04_compare.png')]);
for (const y of [2000, 2020]) rmSync(join(out, `_cmp_${y}.png`));
console.log(`04_compare.png -> ${out}`);
