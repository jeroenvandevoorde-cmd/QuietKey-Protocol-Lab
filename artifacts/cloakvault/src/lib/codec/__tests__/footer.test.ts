/**
 * Footer codec tests: round-trip, checksum, erasure/error limits, bursts,
 * genre-independence, body/footer independence.
 */
import { describe, it, expect } from 'vitest';
import { sha256 } from '@noble/hashes/sha2.js';
import {
  encodePayload,
  decodePayload,
  extractToken,
  wrapToken,
  codecParams,
  RS_PARITY_BYTES,
  SENTINEL,
  ERASURE_MARK,
} from '../footer';
import { BECH32_CHARSET } from '../bech32';
import { renderFooter, createRecoveryPage, recoverFromFooter, CURATED_RECIPES } from '@/lib/pipeline';
import { DeterministicTestRNG } from '@/lib/crypto/rng';
import { FIXED_TEST_MNEMONIC } from '@/lib/crypto/wallet';

/** Deterministic pseudo-random 49-byte capsule-shaped payloads. */
function testCapsule(i: number): Uint8Array {
  const a = sha256(new Uint8Array([0x66, 0x63, i & 0xff, (i >> 8) & 0xff])); // "fc"
  const b = sha256(a);
  const out = new Uint8Array(49);
  out.set(a.slice(0, 32), 0);
  out.set(b.slice(0, 17), 32);
  return out;
}

/** Deterministic PRNG for corruption positions. */
function* prng(seed: number): Generator<number> {
  let s = seed >>> 0 || 1;
  while (true) {
    s ^= s << 13; s >>>= 0;
    s ^= s >> 17;
    s ^= s << 5; s >>>= 0;
    yield s;
  }
}

const P = codecParams();

describe('footer codec parameters', () => {
  it('shipped default: RS(83,49), 34 parity, 133 data chars, 142-char token', () => {
    expect(RS_PARITY_BYTES).toBe(34);
    expect(P.n).toBe(83);
    expect(P.k).toBe(49);
    expect(P.dataChars).toBe(133);
    expect(P.tokenLength).toBe(142);
    expect(P.maxErasures).toBe(34);
    expect(P.maxErrors).toBe(17);
  });
});

describe('round trip', () => {
  it('is identity over 1000 pseudo-random capsules (clean input, zero loss)', () => {
    for (let i = 0; i < 1000; i++) {
      const capsule = testCapsule(i);
      const token = encodePayload(capsule);
      expect(token.length).toBe(P.tokenLength);
      expect(token.startsWith(SENTINEL)).toBe(true);
      const report = decodePayload(token);
      expect(report.decoded).toBe(true);
      expect(report.checksumValid).toBe(true);
      expect(report.errorsCorrected).toBe(0);
      expect(report.erasuresUsed).toBe(0);
      expect([...report.capsule!]).toEqual([...capsule]);
    }
  });
});

describe('Bech32 checksum', () => {
  it('detects corruption of ANY single character (all positions × a substitute)', () => {
    const token = encodePayload(testCapsule(1));
    const body = token.slice(SENTINEL.length);
    for (let pos = 0; pos < body.length; pos++) {
      const orig = body[pos];
      const replacement = BECH32_CHARSET[(BECH32_CHARSET.indexOf(orig) + 1) % 32];
      const corrupted = body.slice(0, pos) + replacement + body.slice(pos + 1);
      const report = decodePayload(SENTINEL + corrupted);
      expect(report.checksumValid).toBe(false); // detected BEFORE RS runs
    }
  });
});

describe('erasure-aware RS at shipped parity', () => {
  it('decodes at the theoretical erasure limit (34 byte-erasures) and fails cleanly beyond', () => {
    const capsule = testCapsule(2);
    const token = encodePayload(capsule);
    const body = [...token.slice(SENTINEL.length)];
    // Erase contiguous chars from a byte-aligned start so char erasures map to
    // exactly 34 distinct codeword bytes: chars 8k..8k+? — erase chars covering
    // bytes 0..33: bits 0..271 → chars 0..54 cover bytes 0..34... use measured
    // approach instead: erase chars one by one until reported erasures == 34.
    let lastGood = null as ReturnType<typeof decodePayload> | null;
    for (let count = 1; count <= body.length; count++) {
      const marked = body.slice();
      for (let j = 0; j < count; j++) marked[j] = ERASURE_MARK;
      const report = decodePayload(SENTINEL + marked.join(''));
      if (report.erasuresUsed <= 34) {
        expect(report.decoded).toBe(true);
        expect([...report.capsule!]).toEqual([...capsule]);
        lastGood = report;
      } else {
        expect(report.decoded).toBe(false);
        expect(report.failure).toMatch(/budget|erasures/i);
        break;
      }
    }
    expect(lastGood).not.toBeNull();
    expect(lastGood!.erasuresUsed).toBe(34); // limit actually reached
  });

  it('burst erasure: a contiguous stain across one wrapped line decodes', () => {
    const capsule = testCapsule(3);
    const token = encodePayload(capsule);
    const lines = wrapToken(token);
    // Destroy 60% of the second line (contiguous burst).
    const damaged = lines
      .map((l, i) => (i === 1 ? ERASURE_MARK.repeat(Math.floor(l.length * 0.6)) + l.slice(Math.floor(l.length * 0.6)) : l))
      .join('\n');
    const report = decodePayload(damaged);
    expect(report.decoded).toBe(true);
    expect([...report.capsule!]).toEqual([...capsule]);
    expect(report.erasuresUsed).toBeGreaterThan(0);
  });

  it('scattered silent errors up to the error budget decode, with counts reported', () => {
    const capsule = testCapsule(4);
    const token = encodePayload(capsule);
    const body = [...token.slice(SENTINEL.length, SENTINEL.length + P.dataChars)];
    const g = prng(42);
    // 8 scattered wrong-but-valid chars at distinct byte-disjoint positions
    // (char spacing ≥ 2 keeps each corrupted char in distinct bytes; ≤16 error bytes).
    const positions = new Set<number>();
    while (positions.size < 8) {
      const pos = g.next().value % P.dataChars;
      if ([...positions].every((p) => Math.abs(p - pos) >= 4)) positions.add(pos);
    }
    for (const pos of positions) {
      const orig = body[pos];
      body[pos] = BECH32_CHARSET[(BECH32_CHARSET.indexOf(orig) + 7) % 32];
    }
    const checksum = token.slice(SENTINEL.length + P.dataChars);
    const report = decodePayload(SENTINEL + body.join('') + checksum);
    expect(report.checksumValid).toBe(false); // checksum flags it first
    expect(report.decoded).toBe(true); // RS still corrects silently-wrong chars
    expect([...report.capsule!]).toEqual([...capsule]);
    expect(report.errorsCorrected).toBeGreaterThanOrEqual(8);
    expect(report.parityBudgetUsed).toBeLessThanOrEqual(34);
  });
});

describe('genre independence (extraction is structure-only)', () => {
  it('the same token extracts and decodes identically from ≥2 different fake footers', () => {
    const capsule = testCapsule(5);
    const token = encodePayload(capsule);
    const wrapped = wrapToken(token).join('\n');
    const footers = [
      `https://arecipeforamaster.com/print?id=${wrapped}&v=1\nPrinted 12/08/2026 · page 1 of 1`,
      `https://tabsandchords.example.net/song/4321/export?fmt=txt&id=${wrapped}&v=1\nguitartabarchive · printed 03/02/2026`,
      `travel notes — day 12\nhttps://wanderfulblog.example.org/entry?id=${wrapped}&v=1`,
    ];
    const reports = footers.map((f) => decodePayload(f));
    for (const r of reports) {
      expect(r.extracted).toBe(true);
      expect(r.decoded).toBe(true);
      expect([...r.capsule!]).toEqual([...capsule]);
    }
    // Identical decode across genres.
    expect(reports.map((r) => [...r.capsule!].join(','))).toEqual(
      Array(footers.length).fill([...capsule].join(',')),
    );
  });

  it('extraction falls back to a length-run when the sentinel itself is damaged', () => {
    const capsule = testCapsule(6);
    const token = encodePayload(capsule);
    const damagedSentinel = ERASURE_MARK.repeat(SENTINEL.length) + token.slice(SENTINEL.length);
    const { token: found, method } = extractToken(`https://x.example/?id=${damagedSentinel}`);
    expect(found).not.toBeNull();
    expect(method).toBe('run');
  });
});

describe('body/footer independence', () => {
  it('changing the recipe body leaves the payload byte-identical, and vice versa', () => {
    const rngA = new DeterministicTestRNG(new Uint8Array(32).fill(9));
    const rngB = new DeterministicTestRNG(new Uint8Array(32).fill(9));
    const pageA = createRecoveryPage(FIXED_TEST_MNEMONIC, rngA, CURATED_RECIPES[0].id);
    const pageB = createRecoveryPage(FIXED_TEST_MNEMONIC, rngB, CURATED_RECIPES[2].id);
    // Same key material (same RNG stream) + different body → identical payload.
    expect(pageB.token).toBe(pageA.token);
    expect(pageB.recipe.body).not.toBe(pageA.recipe.body);
    // And vice versa: different key (→ different payload), same body.
    const rngC = new DeterministicTestRNG(new Uint8Array(32).fill(10));
    const pageC = createRecoveryPage(FIXED_TEST_MNEMONIC, rngC, CURATED_RECIPES[0].id);
    expect(pageC.token).not.toBe(pageA.token);
    expect(pageC.recipe.body).toBe(pageA.recipe.body);
  });

  it('full page round-trip: paste the printed footer lines + Vault Key → mnemonic + fingerprint', () => {
    const rng = new DeterministicTestRNG(new Uint8Array(32).fill(7));
    const page = createRecoveryPage(FIXED_TEST_MNEMONIC, rng);
    const pasted = page.footer.lines.join('\n');
    const rec = recoverFromFooter(pasted, page.vaultKeyText);
    expect(rec.ok).toBe(true);
    expect(rec.mnemonic).toBe(FIXED_TEST_MNEMONIC);
    expect(rec.fingerprint).toBe(page.fingerprint);
    // Wrong key: clean failure, no partial output.
    const bad = recoverFromFooter(pasted, page.vaultKeyText.replace(/.$/, (c) => (c === 'A' ? 'B' : 'A')));
    expect(bad.ok).toBe(false);
    expect(bad.mnemonic).toBeNull();
  });
});
