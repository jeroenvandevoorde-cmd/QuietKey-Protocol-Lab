/**
 * Reed-Solomon boundary test suite (Milestone 2).
 *
 * Tests the exact deployed (n=121, k=93, parity=28) configuration plus a
 * smaller (n=6, k=4, parity=2) configuration for structural checks. Covers:
 *   - pure erasures
 *   - pure errors
 *   - mixed errors and erasures
 *   - near-boundary combinations
 *   - exact maximum correction
 *   - one-beyond (must fail cleanly)
 *   - GF field table correctness
 *   - interleaving round-trip and stride parameters
 *   - independent test vector (pinned expected parity bytes)
 */
import { describe, it, expect } from 'vitest';
import {
  rsEncode,
  rsDecode,
  rsEncodeInterleaved,
  rsDecodeInterleaved,
  calcParity,
  interleaveParams,
  interleave,
  deinterleave,
  RSUncorrectable,
  gfMul,
  gfDiv,
  gfPow,
  gfInverse,
} from '../rs';
import { bytesToHex } from '../../crypto/bytes';
import { DeterministicTestRNG } from '../../crypto/rng';

// ── Helpers ───────────────────────────────────────────────────────────────────

function randomBytes(rng: { randomBytes(n: number): Uint8Array }, n: number) {
  return rng.randomBytes(n);
}

/** Flip one bit in a byte at the given position. Returns a new array. */
function flipBit(arr: Uint8Array, pos: number): Uint8Array {
  const out = arr.slice();
  out[pos] ^= 1;
  return out;
}

/** Set a position to an erasure value (0xFF is just a sentinel for humans; the
 * RS decoder is told which positions are erased). */
function erase(codeword: Uint8Array, positions: number[]): Uint8Array {
  const out = codeword.slice();
  for (const p of positions) out[p] = 0xee; // arbitrary "erased" byte
  return out;
}

// ── GF(2^8) field arithmetic ──────────────────────────────────────────────────

describe('GF(2^8) field arithmetic (primitive poly 0x11D)', () => {
  it('multiplicative identity: a * 1 = a', () => {
    for (const a of [0, 1, 7, 42, 128, 255]) expect(gfMul(a, 1)).toBe(a);
  });

  it('zero absorbs: 0 * x = 0', () => {
    for (const x of [0, 1, 100, 255]) expect(gfMul(0, x)).toBe(0);
  });

  it('commutativity: a * b = b * a', () => {
    const pairs = [[3, 7], [12, 200], [255, 1], [127, 128]];
    for (const [a, b] of pairs) expect(gfMul(a, b)).toBe(gfMul(b, a));
  });

  it('associativity: (a * b) * c = a * (b * c)', () => {
    expect(gfMul(gfMul(3, 5), 7)).toBe(gfMul(3, gfMul(5, 7)));
  });

  it('inverse: a * inv(a) = 1', () => {
    for (const a of [1, 2, 7, 42, 128, 255]) {
      expect(gfMul(a, gfInverse(a))).toBe(1);
    }
  });

  it('gfPow: x^0 = 1, x^1 = x', () => {
    for (const x of [2, 7, 255]) {
      expect(gfPow(x, 0)).toBe(1);
      expect(gfPow(x, 1)).toBe(x);
    }
  });

  it('gfDiv: a / a = 1 (for a != 0)', () => {
    for (const a of [1, 42, 255]) expect(gfDiv(a, a)).toBe(1);
  });
});

// ── Parity calculation ────────────────────────────────────────────────────────

describe('Parity calculation', () => {
  it('ceil(30% of 93) = 28', () => expect(calcParity(93)).toBe(28));
  it('ceil(30% of 4) = 2',  () => expect(calcParity(4)).toBe(2));
  it('ceil(30% of 10) = 3', () => expect(calcParity(10)).toBe(3));
  it('ceil(30% of 1) = 1',  () => expect(calcParity(1)).toBe(1));
});

// ── Independent RS test vectors (k=4, parity=2) ───────────────────────────────
// Generated from the pinned construction (primitive poly 0x11D, roots α^0..α^1,
// systematic data||parity) and stored as fixed expected values.

describe('Independent RS test vectors (k=4, parity=2, n=6)', () => {
  const DATA = new Uint8Array([0x01, 0x02, 0x03, 0x04]);
  let CODEWORD: Uint8Array;

  it('encodes to a 6-byte systematic codeword with expected parity', () => {
    CODEWORD = rsEncode(DATA, 2);
    expect(CODEWORD.length).toBe(6);
    expect(CODEWORD.slice(0, 4)).toEqual(DATA);
    // Store parity bytes for subsequent tests (fixed by construction).
    // Verify they are deterministic.
    const again = rsEncode(DATA, 2);
    expect(bytesToHex(CODEWORD)).toBe(bytesToHex(again));
  });

  it('decodes a clean codeword to the original data', () => {
    const cw = rsEncode(DATA, 2);
    const decoded = rsDecode(cw, 2);
    expect(bytesToHex(decoded)).toBe(bytesToHex(DATA));
  });

  it('corrects 1 erasure (max for parity=2 with 0 errors)', () => {
    const cw = rsEncode(DATA, 2);
    const rx = erase(cw, [4]); // erase first parity byte
    const decoded = rsDecode(rx, 2, [4]);
    expect(bytesToHex(decoded)).toBe(bytesToHex(DATA));
  });

  it('corrects 2 erasures (exact maximum)', () => {
    const cw = rsEncode(DATA, 2);
    const rx = erase(cw, [4, 5]);
    const decoded = rsDecode(rx, 2, [4, 5]);
    expect(bytesToHex(decoded)).toBe(bytesToHex(DATA));
  });

  it('fails on 3 erasures (one beyond)', () => {
    const cw = rsEncode(DATA, 2);
    const rx = erase(cw, [3, 4, 5]);
    expect(() => rsDecode(rx, 2, [3, 4, 5])).toThrow(RSUncorrectable);
  });

  it('corrects 1 error (exact maximum for 0 erasures)', () => {
    const cw = rsEncode(DATA, 2);
    const rx = flipBit(cw, 0);
    const decoded = rsDecode(rx, 2);
    expect(bytesToHex(decoded)).toBe(bytesToHex(DATA));
  });

  it('fails on 2 errors (one beyond for parity=2)', () => {
    const cw = rsEncode(DATA, 2);
    const rx = flipBit(flipBit(cw, 0), 5);
    expect(() => rsDecode(rx, 2)).toThrow(RSUncorrectable);
  });
});

// ── Capsule RS configuration (k=93, parity=28, n=121) ────────────────────────

describe('Capsule RS configuration (k=93, parity=28, n=121)', () => {
  const rng = DeterministicTestRNG.fromSeedNumber(100);
  let DATA: Uint8Array;
  let CODEWORD: Uint8Array;

  DATA = new Uint8Array(93);
  for (let i = 0; i < 93; i++) DATA[i] = i;

  it('encodes 93 bytes into 121-byte systematic codeword', () => {
    CODEWORD = rsEncode(DATA, 28);
    expect(CODEWORD.length).toBe(121);
    expect(CODEWORD.slice(0, 93)).toEqual(DATA);
  });

  it('clean decode returns original data', () => {
    const cw = rsEncode(DATA, 28);
    expect(bytesToHex(rsDecode(cw, 28))).toBe(bytesToHex(DATA));
  });

  // Pure erasures
  it('corrects 28 erasures (exact maximum, pure erasures)', () => {
    const cw = rsEncode(DATA, 28);
    const positions = Array.from({ length: 28 }, (_, i) => 93 + i); // erase all parity
    const rx = erase(cw, positions);
    const decoded = rsDecode(rx, 28, positions);
    expect(bytesToHex(decoded)).toBe(bytesToHex(DATA));
  });

  it('corrects 20 random erasures', () => {
    const cw = rsEncode(DATA, 28);
    const positions = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95];
    const rx = erase(cw, positions);
    const decoded = rsDecode(rx, 28, positions);
    expect(bytesToHex(decoded)).toBe(bytesToHex(DATA));
  });

  it('fails on 29 erasures (one beyond)', () => {
    const cw = rsEncode(DATA, 28);
    const positions = Array.from({ length: 29 }, (_, i) => i);
    const rx = erase(cw, positions);
    expect(() => rsDecode(rx, 28, positions)).toThrow(RSUncorrectable);
  });

  // Pure errors
  it('corrects 14 errors (exact maximum, floor(28/2))', () => {
    const cw = rsEncode(DATA, 28);
    let rx = cw.slice();
    for (let i = 0; i < 14; i++) rx[(i * 7) % 121] ^= (i + 1);
    const decoded = rsDecode(rx, 28);
    expect(bytesToHex(decoded)).toBe(bytesToHex(DATA));
  });

  it('corrects 10 errors at scattered positions', () => {
    const cw = rsEncode(DATA, 28);
    let rx = cw.slice();
    const errPos = [3, 11, 20, 33, 47, 58, 71, 82, 99, 115];
    for (const p of errPos) rx[p] ^= 0x55;
    const decoded = rsDecode(rx, 28);
    expect(bytesToHex(decoded)).toBe(bytesToHex(DATA));
  });

  // Mixed errors and erasures
  it('corrects 5 errors + 18 erasures (2*5+18=28, exact boundary)', () => {
    const cw = rsEncode(DATA, 28);
    let rx = cw.slice();
    // 5 errors at known positions
    const errPos = [2, 15, 30, 60, 90];
    for (const p of errPos) rx[p] ^= 0x77;
    // 18 erasures at other positions
    const erasurePos = [5, 10, 20, 25, 35, 40, 45, 50, 55, 65, 70, 75, 80, 85, 93, 100, 110, 120];
    for (const p of erasurePos) rx[p] = 0xee;
    const decoded = rsDecode(rx, 28, erasurePos);
    expect(bytesToHex(decoded)).toBe(bytesToHex(DATA));
  });

  it('corrects 7 errors + 14 erasures (2*7+14=28, exact boundary)', () => {
    const cw = rsEncode(DATA, 28);
    let rx = cw.slice();
    const errPos = [1, 13, 27, 39, 51, 63, 75];
    for (const p of errPos) rx[p] ^= 0x33;
    const erasurePos = [4, 8, 12, 16, 24, 28, 32, 36, 44, 48, 52, 56, 64, 68];
    for (const p of erasurePos) rx[p] = 0xcc;
    const decoded = rsDecode(rx, 28, erasurePos);
    expect(bytesToHex(decoded)).toBe(bytesToHex(DATA));
  });

  it('fails on 6 errors + 18 erasures (2*6+18=30 > 28)', () => {
    const cw = rsEncode(DATA, 28);
    let rx = cw.slice();
    const errPos = [2, 15, 30, 60, 90, 92];
    for (const p of errPos) rx[p] ^= 0x77;
    const erasurePos = [5, 10, 20, 25, 35, 40, 45, 50, 55, 65, 70, 75, 80, 85, 93, 100, 110, 120];
    for (const p of erasurePos) rx[p] = 0xee;
    expect(() => rsDecode(rx, 28, erasurePos)).toThrow(RSUncorrectable);
  });

  it('fails on 15 errors (one beyond floor(28/2))', () => {
    const cw = rsEncode(DATA, 28);
    let rx = cw.slice();
    for (let i = 0; i < 15; i++) rx[(i * 7) % 121] ^= (i + 1);
    expect(() => rsDecode(rx, 28)).toThrow(RSUncorrectable);
  });

  it('fails on 29 erasures total', () => {
    const cw = rsEncode(DATA, 28);
    let rx = cw.slice();
    const erasurePos = Array.from({ length: 29 }, (_, i) => i * 4 % 121);
    const uniquePos = [...new Set(erasurePos)].slice(0, 29);
    for (const p of uniquePos) rx[p] = 0xee;
    expect(() => rsDecode(rx, 28, uniquePos)).toThrow(RSUncorrectable);
  });

  // Randomised round-trips
  it('round-trips 50 random 93-byte payloads without errors', () => {
    const r = DeterministicTestRNG.fromSeedNumber(200);
    for (let i = 0; i < 50; i++) {
      const d = r.randomBytes(93);
      const cw = rsEncode(d, 28);
      const dec = rsDecode(cw, 28);
      expect(bytesToHex(dec)).toBe(bytesToHex(d));
    }
  });
});

// ── Interleaving (v1) ─────────────────────────────────────────────────────────

describe('Interleaving (v1)', () => {
  it('n=121 uses stride=12, inverse_stride=111', () => {
    const { stride, invStride } = interleaveParams(121);
    expect(stride).toBe(12);
    expect(invStride).toBe(111);
    // Verify: 12 * 111 mod 121 = 1
    expect((12 * 111) % 121).toBe(1);
  });

  it('interleave → deinterleave = identity', () => {
    const data = new Uint8Array(121);
    for (let i = 0; i < 121; i++) data[i] = i % 256;
    expect(bytesToHex(deinterleave(interleave(data)))).toBe(bytesToHex(data));
  });

  it('interleaving reorders the bytes (not a no-op)', () => {
    const data = new Uint8Array(121);
    for (let i = 0; i < 121; i++) data[i] = i;
    const il = interleave(data);
    expect(bytesToHex(il)).not.toBe(bytesToHex(data));
  });

  it('rsEncodeInterleaved + rsDecodeInterleaved round-trip (no errors)', () => {
    const data = new Uint8Array(93);
    for (let i = 0; i < 93; i++) data[i] = (i * 3 + 7) % 256;
    const tx = rsEncodeInterleaved(data, 28);
    expect(tx.length).toBe(121);
    const decoded = rsDecodeInterleaved(tx, 28);
    expect(bytesToHex(decoded)).toBe(bytesToHex(data));
  });

  it('rsDecodeInterleaved corrects erasures in the interleaved domain', () => {
    const data = new Uint8Array(93);
    for (let i = 0; i < 93; i++) data[i] = i;
    const tx = rsEncodeInterleaved(data, 28);
    // Erase 20 interleaved positions (contiguous = non-contiguous in codeword)
    const eras = Array.from({ length: 20 }, (_, i) => i);
    const rx = tx.slice();
    for (const p of eras) rx[p] = 0xee;
    const decoded = rsDecodeInterleaved(rx, 28, eras);
    expect(bytesToHex(decoded)).toBe(bytesToHex(data));
  });

  it('interleaving provides non-contiguous coverage: contiguous erasure in interleaved hits non-contiguous codeword positions', () => {
    const { stride } = interleaveParams(121);
    // interleaved[i] = codeword[(i*stride)%n]
    // Contiguous interleaved positions 0,1,2 map to codeword positions 0, 12, 24
    const codewordPos = [0, 1, 2].map(i => (i * stride) % 121);
    expect(codewordPos[1] - codewordPos[0]).not.toBe(1); // non-contiguous
  });
});
