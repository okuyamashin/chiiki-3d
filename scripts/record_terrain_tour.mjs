// 台本を実時間で再生しながら、Chrome のタブ録画（getDisplayMedia）で動画にする。
//
// ビューアを ?code=<code>&render=1 で開き、ページの window.player.record() に録画を任せる。
// 録画データはページから手元の受け口へ POST で少しずつ受け取ってファイルに書き、最後に ffmpeg で MP4（H.264）にそろえる。
// 画面ありの Chrome が要る（タブ録画はヘッドレスでは動かない）。録画中はそのウィンドウを隠さないこと。
//
// Run:  node scripts/record_terrain_tour.mjs --code 05327 [--size 1920x1080] [--ui 1.5] [--fps 60] [--url http://localhost:8791]
// Out:  output/video/rec_<station>.webm|mp4（録画そのまま）と output/video/rec_<station>_h264.mp4（0秒＝台本の0秒、台本の長さ）

import { chromium } from 'playwright-core';
import { execFileSync } from 'node:child_process';
import { appendFileSync, mkdirSync, readFileSync, rmSync, statSync } from 'node:fs';
import { createServer } from 'node:http';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');  // 公開側のリポジトリ（output/ を共用）
const arg = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : d; };
const station = arg('code', '05327'), fps = +arg('fps', 60), ui = +arg('ui', 1.5);
const [W, H] = arg('size', '1920x1080').split('x').map(Number);
const base = arg('url', 'http://localhost:8791');
const url = `${base}/terrain.html?code=${station}&render=1`;
const data = JSON.parse(readFileSync(join(ROOT, 'output', '3d', `terrain_${station}.json`)));
const tour = JSON.parse(readFileSync(join(ROOT, 'output', '3d', `tour_${station}.json`)));
const files = tour.steps.map(s => { if (!s.audio) throw Error('先に音声生成と台本の再コンパイルが必要です'); return join(ROOT, 'output', '3d', s.audio); });
const durations = files.map(f => +execFileSync('ffprobe', ['-v', 'error', '-show_entries', 'format=duration', '-of', 'csv=p=0', f]).toString());
const title = `${data.name}の地形`;
const out = join(ROOT, 'output', 'video');
mkdirSync(out, { recursive: true });

const browser = await chromium.launch({
  channel: 'chrome', headless: false,
  args: [
    `--auto-select-tab-capture-source-by-title=${title}`, '--auto-accept-this-tab-capture',
    '--enable-gpu', '--ignore-gpu-blocklist', '--disable-background-timer-throttling',
    '--disable-renderer-backgrounding', '--disable-backgrounding-occluded-windows',
    `--window-size=${Math.round(W / ui) + 40},${Math.round(H / ui) + 160}`,
  ],
});
// タブ録画はウィンドウの実際の中身を撮るので、表示の大きさは固定せず、ウィンドウの中身が CSS で W/ui × H/ui になるように合わせる
const page = await browser.newPage({ viewport: null });
const cssW = Math.round(W / ui), cssH = Math.round(H / ui);
page.on('pageerror', (e) => console.error('page error:', e.message));
page.on('console', (m) => { if (m.type() === 'error') console.error('console:', m.text()); });

// 録画データの受け口（ページから届いた順にファイルへ足す）
let file = null;
const server = createServer((req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', '*');
  res.setHeader('Access-Control-Allow-Private-Network', 'true');
  if (req.method !== 'POST') { res.end(); return; }  // 事前確認（OPTIONS）にはヘッダーだけ返す
  const parts = [];
  req.on('data', (c) => parts.push(c));
  req.on('end', () => { appendFileSync(file, Buffer.concat(parts)); res.end('ok'); });
});
await new Promise((r) => server.listen(0, '127.0.0.1', r));
const sink = `http://127.0.0.1:${server.address().port}/chunk`;
await page.goto(url);
await page.waitForFunction(() => window.player, null, { timeout: 120000 });
await page.evaluate(d => window.player.setup(d), durations);
const cdp = await page.context().newCDPSession(page);
const { windowId } = await cdp.send('Browser.getWindowForTarget');
async function fitWindow() {
  for (let k = 0; k < 4; k++) {
    const m = await page.evaluate(() => ({ iw: innerWidth, ih: innerHeight, ow: outerWidth, oh: outerHeight }));
    if (m.iw === cssW && m.ih === cssH) break;
    await cdp.send('Browser.setWindowBounds', { windowId, bounds: { windowState: 'normal', width: cssW + (m.ow - m.iw), height: cssH + (m.oh - m.ih) } });
    await page.waitForTimeout(500);
  }
  return page.evaluate(() => ({ w: innerWidth, h: innerHeight, dpr: devicePixelRatio }));
}
await fitWindow();
await page.bringToFront();
// 先に共有を始める（「このタブを共有中」のバーが出て中身が縮むので、そのあと大きさを合わせ直す）
const cap = await page.evaluate((f) => window.player.capture({ fps: f }), fps);
const size = await fitWindow();
await page.waitForTimeout(1500);  // 建物と地面の準備、共有の安定を待つ
console.log('ウィンドウの中身', size, '共有', cap);
if (size.w !== cssW || size.h !== cssH) console.warn(`注意：中身が ${cssW}x${cssH} になりませんでした（画面が小さい？）`);

const mime = await page.evaluate(() => ['video/mp4;codecs=avc1.640033', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm']
  .find((m) => MediaRecorder.isTypeSupported(m)));
file = join(out, `rec_${station}.${mime.startsWith('video/mp4') ? 'mp4' : 'webm'}`);
rmSync(file, { force: true });
const dur = await page.evaluate(() => window.player.duration);
console.log(`録画開始 ${mime}  ${W}x${H} ${fps}fps  ${(dur / 1000).toFixed(1)} 秒`);
const res = await page.evaluate((o) => window.player.record(o), { bitrate: 24e6, sink });
console.log(`再生にかかった時間 ${(res.wall / 1000).toFixed(2)} 秒  録画の頭のずれ ${res.lead.toFixed(3)} 秒`);
await browser.close();
server.close();

// 録画を調べる（コマ数・長さ）
const probe = (f) => execFileSync('ffprobe', ['-v', 'error', '-select_streams', 'v:0',
  '-show_entries', 'stream=width,height,nb_frames,avg_frame_rate:format=duration', '-of', 'json', f]).toString();
console.log(`録画 ${file} ${(statSync(file).size / 1e6).toFixed(1)} MB`, probe(file));

// 録画の中で左上の目印（マゼンタの四角）が消えた最初のコマを探す。これが台本の0秒。
// 画面の録画には遅れ（0.1秒ほど）があるので、ページの中で測った lead よりこちらが正確
function findSync(f) {
  const pts = execFileSync('ffprobe', ['-v', 'error', '-select_streams', 'v:0', '-read_intervals', '%+5',
    '-show_entries', 'frame=pts_time', '-of', 'csv=p=0', f]).toString().trim().split('\n').map(Number);
  const raw = execFileSync('ffmpeg', ['-loglevel', 'error', '-i', f, '-t', '5', '-fps_mode', 'passthrough',
    '-vf', 'crop=8:8:4:4,format=rgb24', '-f', 'rawvideo', '-'], { maxBuffer: 1 << 26 });
  const n = 8 * 8 * 3;
  let seen = false;
  for (let i = 0; i * n < raw.length && i < pts.length; i++) {
    let r = 0, g = 0, b = 0;
    for (let k = i * n; k < (i + 1) * n; k += 3) { r += raw[k]; g += raw[k + 1]; b += raw[k + 2]; }
    const magenta = r / 64 > 200 && g / 64 < 80 && b / 64 > 200;
    if (magenta) seen = true;
    else if (seen) return pts[i];
  }
  return null;
}
const syncAt = findSync(file);
const lead = syncAt ?? res.lead;
console.log(syncAt != null ? `目印が消えたのは録画の ${syncAt.toFixed(3)} 秒（ページで測ったずれ ${res.lead.toFixed(3)} 秒、画面録画の遅れ ${(syncAt - res.lead).toFixed(3)} 秒）`
  : `注意：目印が見つからないので、ページで測ったずれ ${res.lead.toFixed(3)} 秒で切ります`);

// 頭のずれを切って「動画の0秒＝台本の0秒」にし、台本の長さで終える。YouTube などに合わせて H.264 の固定フレームレートにする
// （ナレーションは台本の時刻のまま ffmpeg で重ねればよい）
const mp4 = join(out, `rec_${station}_h264.mp4`);
execFileSync('ffmpeg', ['-y', '-loglevel', 'error', '-i', file, '-ss', lead.toFixed(3), '-t', (dur / 1000).toFixed(3),
  '-vf', `fps=${fps},scale=${W}:${H}:flags=lanczos,tpad=stop_mode=clone:stop_duration=2`,
  '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', mp4]);
console.log(`→ ${mp4}`, probe(mp4));
