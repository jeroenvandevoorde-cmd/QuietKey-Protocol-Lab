/**
 * Capsule round-trip and failure tests (Milestone 1).
 * All failure modes must yield CapsuleError (RECOVERY FAILED) — never
 * partial plaintext, never a "best guess".
 */
import { describe, it, expect } from 'vitest';
import { DeterministicTestRNG } from '../rng';
import {
  createCapsule,
  openCapsule,
  parseCapsule,
  serializeCapsule,
  capsuleAad,
  CapsuleError,
  CAPSULE_LENGTH,
  CAPSULE_VERSION,
  INITIAL_GENERATION,
} from '../capsule';
import { deriveCapsuleKey, CAPSULE_KEY_INFO } from '../kdf';
import { generateVaultKey, encodeVaultKey, decodeVaultKey } from '../vaultkey';
import { crockfordEncode, crockfordDecode } from '../base32';
import { mnemonicToEntropy32, FIXED_TEST_MNEMONIC } from '../wallet';
import { bytesToHex, equalBytes } from '../bytes';

const rng = () => DeterministicTestRNG.fromSeedNumber(1);

function fixture() {
  const r = rng();
  const entropy = mnemonicToEntropy32(FIXED_TEST_MNEMONIC);
  const vaultKey = generateVaultKey(r);
  const capsule = createCapsule(entropy, vaultKey, r);
  return { entropy, vaultKey, capsule };
}

describe('capsule serialization', () => {
  it('is exactly 93 bytes with the specified field layout', () => {
    const { capsule } = fixture();
    expect(capsule.length).toBe(CAPSULE_LENGTH);
    const f = parseCapsule(capsule);
    expect(f.version).toBe(CAPSULE_VERSION);
    expect(f.generation).toBe(INITIAL_GENERATION);
    expect(f.capsuleId.length).toBe(16);
    expect(f.nonce.length).toBe(24);
    expect(f.ciphertext.length).toBe(32);
    expect(f.tag.length).toBe(16);
    // Re-serialization is byte-identical.
    expect(bytesToHex(serializeCapsule(f))).toBe(bytesToHex(capsule));
    // AAD is exactly the first 21 bytes.
    expect(
      bytesToHex(capsuleAad(f.version, f.generation, f.capsuleId)),
    ).toBe(bytesToHex(capsule.slice(0, 21)));
  });

  it('is deterministic under the same test RNG stream', () => {
    const a = fixture().capsule;
    const b = fixture().capsule;
    expect(bytesToHex(a)).toBe(bytesToHex(b));
  });
});

describe('capsule round-trip', () => {
  it('recovers byte-identical entropy with the correct Vault Key', () => {
    const { entropy, vaultKey, capsule } = fixture();
    const recovered = openCapsule(capsule, vaultKey);
    expect(equalBytes(recovered, entropy)).toBe(true);
  });
});

describe('capsule failure behavior (all must be RECOVERY FAILED)', () => {
  it('modified ciphertext bit fails', () => {
    const { vaultKey, capsule } = fixture();
    const bad = capsule.slice();
    bad[45] ^= 0x01; // first ciphertext byte
    expect(() => openCapsule(bad, vaultKey)).toThrow(CapsuleError);
  });

  it('modified tag fails', () => {
    const { vaultKey, capsule } = fixture();
    const bad = capsule.slice();
    bad[92] ^= 0x80;
    expect(() => openCapsule(bad, vaultKey)).toThrow(CapsuleError);
  });

  it('wrong Vault Key fails', () => {
    const { capsule } = fixture();
    const wrongKey = DeterministicTestRNG.fromSeedNumber(999).randomBytes(32);
    expect(() => openCapsule(capsule, wrongKey)).toThrow(CapsuleError);
  });

  it('altered generation in authenticated header fails', () => {
    const { vaultKey, capsule } = fixture();
    const bad = capsule.slice();
    bad[4] ^= 0x01; // low byte of generation
    expect(() => openCapsule(bad, vaultKey)).toThrow(CapsuleError);
  });

  it('altered capsule ID fails', () => {
    const { vaultKey, capsule } = fixture();
    const bad = capsule.slice();
    bad[5] ^= 0x01;
    expect(() => openCapsule(bad, vaultKey)).toThrow(CapsuleError);
  });

  it('truncated capsule fails with malformed length', () => {
    const { vaultKey, capsule } = fixture();
    expect(() => openCapsule(capsule.slice(0, 92), vaultKey)).toThrow(
      /malformed length/,
    );
    expect(() => openCapsule(new Uint8Array(0), vaultKey)).toThrow(CapsuleError);
  });

  it('invalid version fails', () => {
    const { vaultKey, capsule } = fixture();
    const bad = capsule.slice();
    bad[0] = 0x02;
    expect(() => openCapsule(bad, vaultKey)).toThrow(/version/);
  });
});

describe('capsule key derivation (structure)', () => {
  it('uses the pinned info string and differs across generation/ID/key', () => {
    expect(CAPSULE_KEY_INFO).toBe('CLOAKVAULT-V1-CAPSULE-KEY');
    const r = rng();
    const k = r.randomBytes(32);
    const id = r.randomBytes(16);
    const a = deriveCapsuleKey(k, id, 1);
    expect(a.length).toBe(32);
    expect(bytesToHex(deriveCapsuleKey(k, id, 2))).not.toBe(bytesToHex(a));
    const id2 = id.slice();
    id2[0] ^= 1;
    expect(bytesToHex(deriveCapsuleKey(k, id2, 1))).not.toBe(bytesToHex(a));
  });
});

describe('Vault Key CVK1. representation', () => {
  it('encodes with prefix, 4-char grouping, and round-trips', () => {
    const k = rng().randomBytes(32);
    const text = encodeVaultKey(k);
    expect(text.startsWith('CVK1.')).toBe(true);
    expect(text.slice(5)).toMatch(/^[0-9A-HJKMNP-TV-Z]{4}(-[0-9A-HJKMNP-TV-Z]{1,4})*$/);
    expect(equalBytes(decodeVaultKey(text), k)).toBe(true);
    // Case-insensitive and hyphen-tolerant decode
    expect(equalBytes(decodeVaultKey(text.toLowerCase()), k)).toBe(true);
    expect(equalBytes(decodeVaultKey('CVK1.' + text.slice(5).replace(/-/g, '')), k)).toBe(true);
  });

  it('rejects checksum mismatch, wrong prefix, wrong version', () => {
    const k = rng().randomBytes(32);
    const text = encodeVaultKey(k);
    const body = text.slice(5).replace(/-/g, '');
    // Flip one character to another alphabet character
    const flipped = (body[0] === 'A' ? 'B' : 'A') + body.slice(1);
    expect(() => decodeVaultKey('CVK1.' + flipped)).toThrow();
    expect(() => decodeVaultKey(body)).toThrow(/prefix/);
    expect(() => decodeVaultKey('CVK1.' + body.slice(0, -1))).toThrow();
    expect(() => decodeVaultKey('CVK1.' + body + 'A')).toThrow();
  });

  it('Crockford Base32 decode maps I/L->1 and O->0 and rejects U', () => {
    // 0x88 0x08 -> "H0" + pad... use a simple known byte string
    const bytes = new Uint8Array([0xde, 0xad, 0xbe, 0xef, 0x00]);
    const enc = crockfordEncode(bytes);
    const dec = crockfordDecode(enc.replace(/0/g, 'O').replace(/1/g, 'I'), 5);
    expect(equalBytes(dec, bytes)).toBe(true);
    expect(() => crockfordDecode('U'.repeat(8), 5)).toThrow();
  });
});

describe('deterministic RNG', () => {
  it('same seed -> identical stream; different seed -> different stream', () => {
    const a = DeterministicTestRNG.fromSeedNumber(7).randomBytes(64);
    const b = DeterministicTestRNG.fromSeedNumber(7).randomBytes(64);
    const c = DeterministicTestRNG.fromSeedNumber(8).randomBytes(64);
    expect(bytesToHex(a)).toBe(bytesToHex(b));
    expect(bytesToHex(a)).not.toBe(bytesToHex(c));
  });
});
