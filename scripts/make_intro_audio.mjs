// Synthesize the intro's soundtrack: a quiet pad that opens up as the camera descends, a soft bell when the
// caption appears, a second bell on landing, and a faint wind underneath. No samples, no dependencies.
//
// Timing follows runIntro() in docs/index.html: ~1.2 s hold on Japan, 16 s flight, caption at 35 % of the
// flight, Japan fades into the local scene over the last 18 %, then a hold.
// Run:   node scripts/make_intro_audio.mjs [--len 20.93] [--seed 7]
// Out:   output/audio/intro.wav  (48 kHz, 16-bit stereo)

import { mkdirSync, writeFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const arg = (k, d) => { const i = process.argv.indexOf(`--${k}`); return i > 0 ? process.argv[i + 1] : d; };
const SR = 48000, LEN = +arg('len', 20.93), N = Math.ceil(LEN * SR);
const HOLD = 1.2, FLY = 16, T_CAP = HOLD + FLY * 0.35, T_LAND = HOLD + FLY, T_XF = HOLD + FLY * 0.82;

let seed = +arg('seed', 7);
const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 4294967296);
const cl = x => Math.max(0, Math.min(1, x)), sm = x => { x = cl(x); return x * x * (3 - 2 * x); };
const ramp = (t, a, b) => sm((t - a) / (b - a));

// biquad (RBJ), coefficients updated every block
function biquad() {
  let b0 = 0, b1 = 0, b2 = 0, a1 = 0, a2 = 0, x1 = 0, x2 = 0, y1 = 0, y2 = 0;
  return {
    set(type, f, q) {
      const w = 2 * Math.PI * f / SR, c = Math.cos(w), al = Math.sin(w) / (2 * q), a0 = 1 + al;
      if (type === 'lp') { b0 = (1 - c) / 2; b1 = 1 - c; b2 = b0; } else { b0 = al; b1 = 0; b2 = -al; }  // 'bp'
      b0 /= a0; b1 /= a0; b2 /= a0; a1 = -2 * c / a0; a2 = (1 - al) / a0;
    },
    run(x) { const y = b0 * x + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2; x2 = x1; x1 = x; y2 = y1; y1 = y; return y; },
  };
}
// band-limited saw (polyBLEP)
function saw(freq) {
  let p = rnd();
  const dt = freq / SR, blep = t => t < dt ? (t /= dt, t + t - t * t - 1) : t > 1 - dt ? (t = (t - 1) / dt, t * t + t + t + 1) : 0;
  return () => { const v = 2 * p - 1 - blep(p); p += dt; if (p >= 1) p -= 1; return v; };
}

const L = new Float32Array(N), R = new Float32Array(N);       // dry
const RL = new Float32Array(N), RR = new Float32Array(N);     // reverb send

// ---- pad: D major add9, bright and open, voices entering one by one; the filter opens as the camera comes down ----
const hz = m => 440 * 2 ** ((m - 69) / 12);
const PAD = [  // midi, enter (s), gain, pan
  [38, 0.0, 0.08, 0.0], [50, 0.0, 0.26, -0.2], [57, 0.4, 0.24, 0.3], [62, 1.5, 0.20, -0.4],
  [66, 3.5, 0.18, 0.4], [69, 6.0, 0.13, -0.3], [76, 9.5, 0.08, 0.3], [78, T_LAND - 2.5, 0.07, -0.1],
];
for (const [m, enter, g, pan] of PAD) {
  const osc = [-4, 0, 3].map(c => saw(hz(m) * 2 ** (c / 1200)));
  const lp = biquad(), pl = Math.cos((pan + 1) * Math.PI / 4), pr = Math.sin((pan + 1) * Math.PI / 4);
  for (let i = 0; i < N; i++) {
    const t = i / SR;
    if (i % 64 === 0) {
      const open = ramp(t, HOLD, T_LAND);                      // follows the zoom
      lp.set('lp', 1100 * (1 + 4 * open ** 1.2) * (1 + 0.04 * Math.sin(t * 0.7 + m)), 0.6);
    }
    const env = ramp(t, enter, enter + 3.5) * (1 - ramp(t, LEN - 3.2, LEN - 0.05));
    if (env <= 0) continue;
    const v = lp.run((osc[0]() + osc[1]() + osc[2]()) / 3) * g * env * (0.9 + 0.1 * Math.sin(t * 0.31 + m));
    L[i] += v * pl; R[i] += v * pr; RL[i] += v * pl * 0.5; RR[i] += v * pr * 0.5;
  }
}

// ---- bells: soft glassy tones with harmonic overtones, mostly in the reverb ----
function bell(at, freqs, gain) {
  for (const [f, pan, g] of freqs) {
    const pl = Math.cos((pan + 1) * Math.PI / 4), pr = Math.sin((pan + 1) * Math.PI / 4);
    for (let i = Math.floor(at * SR); i < N; i++) {
      const t = i / SR - at, env = Math.min(1, t / 0.004) * Math.exp(-t / 1.9);
      if (t > 0.1 && env < 1e-4) break;
      const idx = 0.8 * Math.exp(-t / 0.3);
      const v = Math.sin(2 * Math.PI * f * t + idx * Math.sin(2 * Math.PI * f * 2 * t)) * env * gain * g;
      L[i] += v * pl * 0.8; R[i] += v * pr * 0.8; RL[i] += v * pl; RR[i] += v * pr;
    }
  }
}
bell(T_CAP, [[hz(78), -0.3, 1]], 0.28); bell(T_CAP + 0.18, [[hz(81), 0.3, 1], [hz(81) * 2.01, 0, 0.1]], 0.28);  // F#5 -> A5, caption
[74, 78, 81, 86].forEach((m, k) => bell(T_XF + 0.6 + k * 0.14, [[hz(m), -0.4 + k * 0.27, 1]], 0.24));  // D-F#-A-D rising, landing

// ---- wind: filtered noise with slow gusts, a little louder at the start and as we approach the ground ----
{
  const bpL = biquad(), bpR = biquad(), lpL = biquad(), lpR = biquad();
  lpL.set('lp', 1400, 0.7); lpR.set('lp', 1400, 0.7);
  let g1 = 0, g2 = 0, gust = 0.5, f = 500;
  for (let i = 0; i < N; i++) {
    const t = i / SR;
    if (i % 64 === 0) {
      g1 += (rnd() - 0.5) * 0.02; g1 *= 0.995; g2 += (rnd() - 0.5) * 0.008; g2 *= 0.999;
      gust = cl(0.55 + 2.2 * g1 + 4 * g2);
      f = 380 + 520 * gust;
      bpL.set('bp', f, 0.9); bpR.set('bp', f * 1.07, 0.9);
    }
    const shape = 0.55 + 0.45 * Math.max(1 - ramp(t, 0, 6), ramp(t, T_XF - 3, T_XF + 1) * (1 - ramp(t, T_LAND + 0.5, LEN)));
    const env = ramp(t, 0, 2.0) * (1 - ramp(t, LEN - 2.5, LEN - 0.05)) * shape * (0.35 + 0.65 * gust) * 0.035;
    L[i] += lpL.run(bpL.run(rnd() * 2 - 1)) * env;
    R[i] += lpR.run(bpR.run(rnd() * 2 - 1)) * env;
  }
}

// ---- reverb (Freeverb-style: 8 combs + 4 allpasses per side) ----
function reverb(x, spread) {
  const y = new Float32Array(N);
  const combs = [1116, 1188, 1277, 1356, 1422, 1491, 1557, 1617].map(d => ({ b: new Float32Array(Math.round((d + spread) * SR / 44100 * 1.6)), i: 0, s: 0 }));
  const aps = [556, 441, 341, 225].map(d => ({ b: new Float32Array(Math.round((d + spread) * SR / 44100)), i: 0 }));
  for (let n = 0; n < N; n++) {
    let o = 0;
    for (const c of combs) {
      const v = c.b[c.i]; c.s = v * 0.75 + c.s * 0.25; c.b[c.i] = x[n] * 0.03 + c.s * 0.86; c.i = (c.i + 1) % c.b.length; o += v;
    }
    for (const a of aps) { const v = a.b[a.i]; a.b[a.i] = o + v * 0.5; o = v - o; a.i = (a.i + 1) % a.b.length; }
    y[n] = o;
  }
  return y;
}
const wl = reverb(RL, 0), wr = reverb(RR, 23);
for (let i = 0; i < N; i++) { L[i] += wl[i] * 0.9; R[i] += wr[i] * 0.9; }

// ---- master: gentle low cut, normalize to -3 dBFS, 16-bit WAV ----
let hpL = 0, hpR = 0, pxL = 0, pxR = 0, peak = 0;
const k = Math.exp(-2 * Math.PI * 55 / SR);
for (let i = 0; i < N; i++) {
  hpL = k * (hpL + L[i] - pxL); pxL = L[i]; L[i] = hpL;
  hpR = k * (hpR + R[i] - pxR); pxR = R[i]; R[i] = hpR;
  peak = Math.max(peak, Math.abs(L[i]), Math.abs(R[i]));
}
const gain = 10 ** (-3 / 20) / peak, buf = Buffer.alloc(44 + N * 4);
buf.write('RIFF', 0); buf.writeUInt32LE(36 + N * 4, 4); buf.write('WAVEfmt ', 8); buf.writeUInt32LE(16, 16);
buf.writeUInt16LE(1, 20); buf.writeUInt16LE(2, 22); buf.writeUInt32LE(SR, 24); buf.writeUInt32LE(SR * 4, 28);
buf.writeUInt16LE(4, 32); buf.writeUInt16LE(16, 34); buf.write('data', 36); buf.writeUInt32LE(N * 4, 40);
for (let i = 0; i < N; i++) {
  buf.writeInt16LE(Math.round(cl((L[i] * gain + 1) / 2) * 65534 - 32767), 44 + i * 4);
  buf.writeInt16LE(Math.round(cl((R[i] * gain + 1) / 2) * 65534 - 32767), 46 + i * 4);
}
const out = join(ROOT, 'output', 'audio', 'intro.wav');
mkdirSync(dirname(out), { recursive: true }); writeFileSync(out, buf);
console.log(`caption bell ${T_CAP.toFixed(1)} s, landing bell ${(T_XF + 0.6).toFixed(1)} s, ${LEN} s -> ${out}`);
