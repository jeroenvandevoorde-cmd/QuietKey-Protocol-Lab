/**
 * CloakVault v3 damage harness (dev tool, NOT a runtime feature).
 *
 * Encodes known capsules, renders footer tokens, applies the six physical-
 * damage models as character-level corruption, and reports decode success
 * plus erasure/error counts per parity setting — the evidence base for
 * tuning RS_PARITY_BYTES.
 *
 * Damage models (from the paper test):
 *   coffee  — one contiguous run of KNOWN-MISSING chars ('?')          [erasures]
 *   scratch — narrow contiguous known-missing run                      [erasures]
 *   crumple — several short scattered known-missing runs               [erasures]
 *   scuff   — scattered wrong-but-valid chars at unknown positions     [errors]
 *   fade    — widespread scattered wrong-but-valid chars               [errors]
 *   crease  — one contiguous run of wrong-but-valid chars              [errors]
 *
 * Run: cd artifacts/cloakvault && npx tsx scripts/damage-harness.ts
 */
import { sha256 } from '@noble/hashes/sha2.js';
import { encodePayload, decodePayload, codecParams, SENTINEL, ERASURE_MARK } from '../src/lib/codec/footer';
import { BECH32_CHARSET } from '../src/lib/codec/bech32';

const PARITY_SETTINGS = [16, 24, 34];
const SEEDS = 200;

function testCapsule(i: number): Uint8Array {
  const a = sha256(new Uint8Array([0x64, 0x68, i & 0xff, (i >> 8) & 0xff])); // "dh"
  const b = sha256(a);
  const out = new Uint8Array(49);
  out.set(a.slice(0, 32), 0);
  out.set(b.slice(0, 17), 32);
  return out;
}

function makePrng(seed: number) {
  let s = (seed * 2654435761) >>> 0 || 1;
  return () => {
    s ^= s << 13; s >>>= 0;
    s ^= s >> 17;
    s ^= s << 5; s >>>= 0;
    return s;
  };
}

type Damage = (body: string[], size: number, rnd: () => number) => void;

const wrongChar = (c: string, rnd: () => number) => {
  const i = BECH32_CHARSET.indexOf(c);
  return BECH32_CHARSET[(i + 1 + (rnd() % 30)) % 32];
};

const MODELS: Record<string, { kind: 'erasure' | 'error'; apply: Damage }> = {
  coffee: {
    kind: 'erasure',
    apply: (b, size, rnd) => {
      const start = rnd() % Math.max(1, b.length - size);
      for (let i = start; i < start + size; i++) b[i] = ERASURE_MARK;
    },
  },
  scratch: {
    kind: 'erasure',
    apply: (b, size, rnd) => {
      const start = rnd() % Math.max(1, b.length - size);
      for (let i = start; i < start + size; i++) b[i] = ERASURE_MARK;
    },
  },
  crumple: {
    kind: 'erasure',
    apply: (b, size, rnd) => {
      const runs = 4;
      const runLen = Math.max(1, Math.floor(size / runs));
      for (let r = 0; r < runs; r++) {
        const start = rnd() % Math.max(1, b.length - runLen);
        for (let i = start; i < start + runLen; i++) b[i] = ERASURE_MARK;
      }
    },
  },
  scuff: {
    kind: 'error',
    apply: (b, size, rnd) => {
      for (let j = 0; j < size; j++) {
        const pos = rnd() % b.length;
        if (b[pos] !== ERASURE_MARK) b[pos] = wrongChar(b[pos], rnd);
      }
    },
  },
  fade: {
    kind: 'error',
    apply: (b, size, rnd) => {
      // widespread: strided positions across the whole token
      const stride = Math.max(2, Math.floor(b.length / Math.max(1, size)));
      for (let pos = rnd() % stride; pos < b.length && size-- > 0; pos += stride) {
        b[pos] = wrongChar(b[pos], rnd);
      }
    },
  },
  crease: {
    kind: 'error',
    apply: (b, size, rnd) => {
      const start = rnd() % Math.max(1, b.length - size);
      for (let i = start; i < start + size; i++) b[i] = wrongChar(b[i], rnd);
    },
  },
};

// Damage sizes in characters, per model kind (erasure chars are cheap; error chars cost 2×).
const SIZES = [4, 8, 12, 16, 20, 26, 32, 40, 48];

console.log('CloakVault v3 damage harness');
console.log(`seeds per cell: ${SEEDS}\n`);

for (const parity of PARITY_SETTINGS) {
  const p = codecParams(parity);
  console.log(`── parity ${parity} → RS(${p.n},${p.k}), token ${p.tokenLength} chars, budget 2e+s ≤ ${parity} ──`);
  console.log('model    kind     ' + SIZES.map((s) => String(s).padStart(6)).join(''));
  for (const [name, model] of Object.entries(MODELS)) {
    const cells: string[] = [];
    for (const size of SIZES) {
      let ok = 0;
      let sumE = 0;
      let sumErr = 0;
      for (let seed = 0; seed < SEEDS; seed++) {
        const capsule = testCapsule(seed);
        const token = encodePayload(capsule, parity);
        const body = [...token.slice(SENTINEL.length)];
        const rnd = makePrng(seed * 1000 + size);
        model.apply(body, size, rnd);
        const report = decodePayload(SENTINEL + body.join(''), parity);
        if (report.decoded && report.capsule && report.capsule.every((v, i) => v === capsule[i])) {
          ok++;
          sumE += report.erasuresUsed;
          sumErr += report.errorsCorrected;
        }
      }
      const rate = ok / SEEDS;
      const avgE = ok ? (sumE / ok).toFixed(0) : '-';
      const avgErr = ok ? (sumErr / ok).toFixed(0) : '-';
      cells.push(`${(rate * 100).toFixed(0)}%`.padStart(6));
      if (size === SIZES[SIZES.length - 1] && false) console.log(avgE, avgErr);
    }
    console.log(`${name.padEnd(9)}${model.kind.padEnd(9)}${cells.join('')}`);
  }
  console.log('');
}
console.log('cells = decode success rate at damage size (chars). erasure models mark chars as "?";');
console.log('error models write wrong-but-valid chars. 2·errorBytes + erasureBytes ≤ parity governs.');
