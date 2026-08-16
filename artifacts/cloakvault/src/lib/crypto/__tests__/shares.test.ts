/**
 * Legacy v1 shares (superseded) — regression tests.
 *
 * Purpose: verify that retained legacy v1 behavior remains internally
 * stable — NOT to prove current Independent Recovery. The current QK2-04
 * Independent Recovery format (64-byte VaultKey ‖ keyB) is a later Gate-B
 * deliverable and is intentionally not implemented here.
 */
import { describe, it, expect } from 'vitest';
import { DeterministicTestRNG } from '../rng';
import { generateVaultKey, encodeVaultKey, decodeVaultKey } from '../vaultkey';
import {
  createShares,
  rejoinShares,
  ShareError,
  SHARE_A_PREFIX,
  SHARE_B_PREFIX,
} from '../shares';
import { equalBytes } from '../bytes';

const rng = () => DeterministicTestRNG.fromSeedNumber(42);

function fixture(gen = 1) {
  const r = rng();
  const k = generateVaultKey(r);
  const { shareA, shareB } = createShares(k, r, gen);
  return { k, shareA, shareB };
}

describe('legacy v1 shares (superseded) — share creation', () => {
  it('CVSA1./CVSB1. prefixes are present', () => {
    const { shareA, shareB } = fixture();
    expect(shareA.startsWith(SHARE_A_PREFIX)).toBe(true);
    expect(shareB.startsWith(SHARE_B_PREFIX)).toBe(true);
  });

  it('deterministic under the same test RNG', () => {
    const a = fixture();
    const b = fixture();
    expect(a.shareA).toBe(b.shareA);
    expect(a.shareB).toBe(b.shareB);
  });
});

describe('legacy v1 shares (superseded) — rejoin round-trip', () => {
  it('reconstructs the original Vault Key exactly', () => {
    const { k, shareA, shareB } = fixture();
    const cvk = rejoinShares(shareA, shareB);
    const recovered = decodeVaultKey(cvk);
    expect(equalBytes(recovered, k)).toBe(true);
  });

  it('is independent of generation number', () => {
    for (const gen of [1, 2, 100, 0xffffffff]) {
      const r = rng();
      const k = generateVaultKey(r);
      const { shareA, shareB } = createShares(k, r, gen);
      const cvk = rejoinShares(shareA, shareB);
      expect(equalBytes(decodeVaultKey(cvk), k)).toBe(true);
    }
  });
});

describe('legacy v1 shares (superseded) — validation errors (exact messages)', () => {
  it('detects wrong share A checksum (corrupt a middle character)', () => {
    const { shareA, shareB } = fixture();
    // Flip a character in the middle of the body (not the last char, which could
    // trigger a base32 padding error rather than a checksum error).
    const body = shareA.slice(SHARE_A_PREFIX.length).replace(/-/g, '');
    const mid = Math.floor(body.length / 2);
    const flipped = body.slice(0, mid) + (body[mid] === 'A' ? 'B' : 'A') + body.slice(mid + 1);
    const bad = SHARE_A_PREFIX + flipped;
    expect(() => rejoinShares(bad, shareB)).toThrow(ShareError);
    expect(() => rejoinShares(bad, shareB)).toThrow(/checksum/i);
  });

  it('detects wrong share B checksum (corrupt a middle character)', () => {
    const { shareA, shareB } = fixture();
    const body = shareB.slice(SHARE_B_PREFIX.length).replace(/-/g, '');
    const mid = Math.floor(body.length / 2);
    const flipped = body.slice(0, mid) + (body[mid] === 'A' ? 'B' : 'A') + body.slice(mid + 1);
    const bad = SHARE_B_PREFIX + flipped;
    expect(() => rejoinShares(shareA, bad)).toThrow(ShareError);
    expect(() => rejoinShares(shareA, bad)).toThrow(/checksum/i);
  });

  it('detects both inputs are Share A', () => {
    const { shareA } = fixture();
    expect(() => rejoinShares(shareA, shareA)).toThrow(/Both inputs are Share A/);
  });

  it('detects both inputs are Share B', () => {
    const { shareB } = fixture();
    expect(() => rejoinShares(shareB, shareB)).toThrow(/Both inputs are Share B/);
  });

  it('detects generation mismatch', () => {
    const r1 = rng();
    const k = generateVaultKey(r1);
    const { shareA } = createShares(k, r1, 1);
    const r2 = rng();
    const k2 = generateVaultKey(r2);
    const { shareB } = createShares(k2, r2, 2);
    expect(() => rejoinShares(shareA, shareB)).toThrow(/Generation mismatch/);
  });

  it('rejects missing prefix', () => {
    const { shareA, shareB } = fixture();
    expect(() => rejoinShares('garbage', shareB)).toThrow();
    expect(() => rejoinShares(shareA, 'garbage')).toThrow();
  });
});
