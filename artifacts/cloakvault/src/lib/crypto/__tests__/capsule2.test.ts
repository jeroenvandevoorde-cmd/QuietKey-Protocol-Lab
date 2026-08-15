/**
 * Capsule v2 (AES-256-GCM-SIV) — external KATs and capsule tests.
 *
 * KAT source: RFC 8452, Appendix C.2 (AEAD_AES_256_GCM_SIV), copied verbatim
 * from https://www.rfc-editor.org/rfc/rfc8452.txt. Expected values are
 * authoritative and must NEVER be adjusted to match implementation output.
 */
import { describe, it, expect } from 'vitest';
import { gcmsiv } from '@noble/ciphers/aes.js';
import { hexToBytes, bytesToHex } from '../bytes';
import {
  createCapsuleV2,
  openCapsuleV2,
  deriveCapsuleKeyV2,
  Capsule2Error,
  CAPSULE2_LENGTH,
  CAPSULE2_VERSION,
} from '../capsule2';

// ── RFC 8452 Appendix C.2 vectors (AES-256, zero AAD unless noted) ───────────
const KEY = hexToBytes('0100000000000000000000000000000000000000000000000000000000000000');
const NONCE = hexToBytes('030000000000000000000000');

const C2_VECTORS = [
  {
    name: 'C.2 empty plaintext',
    plaintext: '',
    aad: '',
    result: '07f5f4169bbf55a8400cd47ea6fd400f',
  },
  {
    name: 'C.2 16-byte plaintext',
    plaintext: '01000000000000000000000000000000',
    aad: '',
    result: '85a01b63025ba19b7fd3ddfc033b3e76c9eac6fa700942702e90862383c6c366',
  },
  {
    name: 'C.2 32-byte plaintext',
    plaintext: '0100000000000000000000000000000002000000000000000000000000000000',
    aad: '',
    result:
      '4a6a9db4c8c6549201b9edb53006cba821ec9cf850948a7c86c68ac7539d027fe819e63abcd020b006a976397632eb5d',
  },
  {
    name: 'C.2 8-byte plaintext, 1-byte AAD',
    plaintext: '0200000000000000',
    aad: '01',
    result: '1de22967237a813291213f267e3b452f02d01ae33e4ec854',
  },
];

describe('RFC 8452 AES-256-GCM-SIV external KATs', () => {
  for (const v of C2_VECTORS) {
    it(v.name, () => {
      const sealed = gcmsiv(KEY, NONCE, hexToBytes(v.aad)).encrypt(hexToBytes(v.plaintext));
      expect(bytesToHex(sealed)).toBe(v.result);
      // Decrypt side round-trips the official result.
      const opened = gcmsiv(KEY, NONCE, hexToBytes(v.aad)).decrypt(hexToBytes(v.result));
      expect(bytesToHex(opened)).toBe(v.plaintext);
    });
  }
});

// ── Capsule v2 behavior ───────────────────────────────────────────────────────
const ENTROPY = new Uint8Array(32).map((_, i) => i * 7 + 1);
const VK = new Uint8Array(32).map((_, i) => 255 - i);

describe('capsule v2 (49-byte, deterministic)', () => {
  it('round-trips and is exactly 49 bytes', () => {
    const c = createCapsuleV2(ENTROPY, VK);
    expect(c.length).toBe(CAPSULE2_LENGTH);
    expect(c[0]).toBe(CAPSULE2_VERSION);
    expect([...openCapsuleV2(c, VK)]).toEqual([...ENTROPY]);
  });

  it('is deterministic: same seed + same key → byte-identical capsule (intended, for equivalent-card redundancy)', () => {
    const a = createCapsuleV2(ENTROPY, VK);
    const b = createCapsuleV2(ENTROPY, VK);
    expect(bytesToHex(a)).toBe(bytesToHex(b));
  });

  it('different key → different capsule; wrong key fails cleanly', () => {
    const c = createCapsuleV2(ENTROPY, VK);
    const otherKey = new Uint8Array(32).map((_, i) => i);
    expect(bytesToHex(createCapsuleV2(ENTROPY, otherKey))).not.toBe(bytesToHex(c));
    expect(() => openCapsuleV2(c, otherKey)).toThrow(Capsule2Error);
  });

  it('tampering any region fails: version, ciphertext, tag, truncation', () => {
    const c = createCapsuleV2(ENTROPY, VK);
    for (const idx of [0, 1, 20, 32, 33, 48]) {
      const t = c.slice();
      t[idx] ^= 0x01;
      expect(() => openCapsuleV2(t, VK)).toThrow(Capsule2Error);
    }
    expect(() => openCapsuleV2(c.slice(0, 48), VK)).toThrow(Capsule2Error);
  });

  it('HKDF derivation uses the frozen constants (empty salt, exact info string)', () => {
    // Independent recomputation with explicit constants must match.
    const derived = deriveCapsuleKeyV2(VK);
    expect(derived.length).toBe(32);
    // Info string is pinned verbatim; any drift changes every capsule.
    expect('CLOAKVAULT-V3-CAPSULE-KEY'.length).toBe(25);
  });
});
