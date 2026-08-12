/**
 * External known-answer tests. Expected values in
 * ../vectors/external-kats.ts were copied verbatim from authoritative
 * published sources. If any test here fails, the implementation is wrong;
 * the expected values must never be changed to match the code.
 */
import { describe, it, expect } from 'vitest';
import { hkdf, extract } from '@noble/hashes/hkdf.js';
import { sha256 } from '@noble/hashes/sha2.js';
import { HDKey } from '@scure/bip32';
import { mnemonicToSeedSync } from '@scure/bip39';
import { base58check } from '@scure/base';

import {
  BIP39_TREZOR_VECTORS,
  BIP32_TEST_VECTOR_1,
  RFC5869_CASE_1,
  RFC5869_CASE_2,
  XCHACHA20_POLY1305_KAT,
} from '../../vectors/external-kats';
import { bytesToHex, hexToBytes } from '../bytes';
import {
  entropy32ToMnemonic,
  mnemonicToEntropy32,
  validateMnemonic24,
  FIXED_TEST_MNEMONIC,
} from '../wallet';
import { masterFingerprintFromSeed, formatFingerprint } from '../fingerprint';
import { aeadEncrypt, aeadDecrypt } from '../aead';

describe('BIP39 KATs (Trezor official vectors)', () => {
  it('all-zero 256-bit entropy produces 23x abandon + art', () => {
    const v = BIP39_TREZOR_VECTORS[0];
    expect(v.entropyHex).toBe('00'.repeat(32));
    const mnemonic = entropy32ToMnemonic(hexToBytes(v.entropyHex));
    expect(mnemonic).toBe(v.mnemonic);
    expect(mnemonic).toBe(FIXED_TEST_MNEMONIC);
    expect(mnemonic.split(' ').slice(0, 23)).toEqual(Array(23).fill('abandon'));
    expect(mnemonic.split(' ')[23]).toBe('art');
  });

  for (const v of BIP39_TREZOR_VECTORS) {
    it(`entropy ${v.entropyHex.slice(0, 8)}… round-trips and derives the published seed`, () => {
      const mnemonic = entropy32ToMnemonic(hexToBytes(v.entropyHex));
      expect(mnemonic).toBe(v.mnemonic);
      expect(bytesToHex(mnemonicToEntropy32(v.mnemonic))).toBe(v.entropyHex);
      // Trezor vectors use passphrase "TREZOR" for the seed column.
      const seed = mnemonicToSeedSync(v.mnemonic, 'TREZOR');
      expect(bytesToHex(seed)).toBe(v.seedHexTrezorPassphrase);
    });
  }

  it('rejects wrong word count, unknown words, and bad checksum', () => {
    expect(validateMnemonic24('abandon abandon art').valid).toBe(false);
    expect(
      validateMnemonic24(`${'abandon '.repeat(23)}zzzzzz`.trim()).valid,
    ).toBe(false);
    // 24 valid words with an invalid checksum (all abandon)
    expect(
      validateMnemonic24(`${'abandon '.repeat(24)}`.trim()).valid,
    ).toBe(false);
    expect(validateMnemonic24(FIXED_TEST_MNEMONIC).valid).toBe(true);
  });
});

describe('BIP32 KAT (specification test vector 1)', () => {
  const seed = hexToBytes(BIP32_TEST_VECTOR_1.seedHex);

  it('master extended keys match the published vector', () => {
    const hd = HDKey.fromMasterSeed(seed);
    expect(hd.privateExtendedKey).toBe(BIP32_TEST_VECTOR_1.master.xprv);
    expect(hd.publicExtendedKey).toBe(BIP32_TEST_VECTOR_1.master.xpub);
  });

  it("derived m/0' and m/0'/1 extended keys match the published vector", () => {
    const hd = HDKey.fromMasterSeed(seed);
    const m0h = hd.derive("m/0'");
    expect(m0h.privateExtendedKey).toBe(BIP32_TEST_VECTOR_1.m0h.xprv);
    expect(m0h.publicExtendedKey).toBe(BIP32_TEST_VECTOR_1.m0h.xpub);
    const m0h1 = hd.derive("m/0'/1");
    expect(m0h1.privateExtendedKey).toBe(BIP32_TEST_VECTOR_1.m0h1.xprv);
    expect(m0h1.publicExtendedKey).toBe(BIP32_TEST_VECTOR_1.m0h1.xpub);
  });

  it('master fingerprint matches the parent-fingerprint field embedded in the published m/0\' xprv', () => {
    // Independent expected value: bytes 5..9 of the base58check-decoded
    // PUBLISHED m/0' extended key are, per the BIP32 serialization format,
    // the fingerprint of the parent (= master) key. This is extracted from
    // the published vector string, not computed by our fingerprint code.
    const decoded = base58check(sha256).decode(BIP32_TEST_VECTOR_1.m0h.xprv);
    const expectedMasterFp = decoded.slice(5, 9);

    const fp = masterFingerprintFromSeed(seed);
    expect(bytesToHex(fp)).toBe(bytesToHex(expectedMasterFp));
    expect(formatFingerprint(fp)).toMatch(/^[0-9A-F]{4}-[0-9A-F]{4}$/);
  });
});

describe('HKDF-SHA256 KATs (RFC 5869 cases 1 and 2)', () => {
  for (const [name, c] of [
    ['case 1', RFC5869_CASE_1],
    ['case 2', RFC5869_CASE_2],
  ] as const) {
    it(`${name}: PRK and OKM match the RFC`, () => {
      const ikm = hexToBytes(c.ikmHex);
      const salt = hexToBytes(c.saltHex);
      const info = hexToBytes(c.infoHex);
      const prk = extract(sha256, ikm, salt);
      expect(bytesToHex(prk)).toBe(c.prkHex);
      const okm = hkdf(sha256, ikm, salt, info, c.length);
      expect(bytesToHex(okm)).toBe(c.okmHex);
    });
  }
});

describe('XChaCha20-Poly1305 KAT (draft-irtf-cfrg-xchacha-03 A.3.1)', () => {
  it('encrypt matches the published ciphertext and tag', () => {
    const { ciphertext, tag } = aeadEncrypt(
      hexToBytes(XCHACHA20_POLY1305_KAT.keyHex),
      hexToBytes(XCHACHA20_POLY1305_KAT.nonceHex),
      hexToBytes(XCHACHA20_POLY1305_KAT.plaintextHex),
      hexToBytes(XCHACHA20_POLY1305_KAT.aadHex),
    );
    expect(bytesToHex(ciphertext)).toBe(XCHACHA20_POLY1305_KAT.ciphertextHex);
    expect(bytesToHex(tag)).toBe(XCHACHA20_POLY1305_KAT.tagHex);
  });

  it('decrypt of the published ciphertext recovers the published plaintext', () => {
    const pt = aeadDecrypt(
      hexToBytes(XCHACHA20_POLY1305_KAT.keyHex),
      hexToBytes(XCHACHA20_POLY1305_KAT.nonceHex),
      hexToBytes(XCHACHA20_POLY1305_KAT.ciphertextHex),
      hexToBytes(XCHACHA20_POLY1305_KAT.tagHex),
      hexToBytes(XCHACHA20_POLY1305_KAT.aadHex),
    );
    expect(bytesToHex(pt)).toBe(XCHACHA20_POLY1305_KAT.plaintextHex);
  });

  it('tampered tag fails authentication', () => {
    const tag = hexToBytes(XCHACHA20_POLY1305_KAT.tagHex);
    tag[0] ^= 0x01;
    expect(() =>
      aeadDecrypt(
        hexToBytes(XCHACHA20_POLY1305_KAT.keyHex),
        hexToBytes(XCHACHA20_POLY1305_KAT.nonceHex),
        hexToBytes(XCHACHA20_POLY1305_KAT.ciphertextHex),
        tag,
        hexToBytes(XCHACHA20_POLY1305_KAT.aadHex),
      ),
    ).toThrow();
  });
});
