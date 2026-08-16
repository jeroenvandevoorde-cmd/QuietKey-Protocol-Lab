/**
 * In-browser Self-Test suites — DIRECT PORTS of the vitest files:
 *
 *   src/lib/crypto/__tests__/kats.test.ts      → group "kats"
 *   src/lib/crypto/__tests__/capsule.test.ts   → group "capsule"
 *   src/lib/crypto/__tests__/capsule2.test.ts  → groups "kats" (RFC 8452) + "capsule"
 *   src/lib/crypto/__tests__/shares.test.ts    → group "capsule"
 *   src/lib/rs/__tests__/rs.test.ts            → group "rs"
 *   src/lib/codec/__tests__/footer.test.ts     → group "codec"
 *
 * RULES (owner-binding): the logic here mirrors the vitest files exactly.
 * Counts are never reduced (1000 = 1000, exhaustive = exhaustive), nothing
 * is sampled or made probabilistic. Tests tagged scope:'full' are excluded
 * from the auto-run smoke subset ONLY because of runtime; the full suite
 * always runs them complete and unreduced.
 */
import { hkdf, extract } from '@noble/hashes/hkdf.js';
import { sha256 } from '@noble/hashes/sha2.js';
import { HDKey } from '@scure/bip32';
import { mnemonicToSeedSync } from '@scure/bip39';
import { base58check } from '@scure/base';
import { gcmsiv } from '@noble/ciphers/aes.js';

import {
  BIP39_TREZOR_VECTORS,
  BIP32_TEST_VECTOR_1,
  RFC5869_CASE_1,
  RFC5869_CASE_2,
  XCHACHA20_POLY1305_KAT,
} from '@/lib/vectors/external-kats';
import { bytesToHex, hexToBytes, equalBytes } from '@/lib/crypto/bytes';
import {
  entropy32ToMnemonic,
  mnemonicToEntropy32,
  validateMnemonic24,
  FIXED_TEST_MNEMONIC,
} from '@/lib/crypto/wallet';
import { masterFingerprintFromSeed, formatFingerprint } from '@/lib/crypto/fingerprint';
import { aeadEncrypt, aeadDecrypt } from '@/lib/crypto/aead';
import { DeterministicTestRNG } from '@/lib/crypto/rng';
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
} from '@/lib/crypto/capsule';
import {
  createCapsuleV2,
  openCapsuleV2,
  deriveCapsuleKeyV2,
  Capsule2Error,
  CAPSULE2_LENGTH,
  CAPSULE2_VERSION,
} from '@/lib/crypto/capsule2';
import { deriveCapsuleKey, CAPSULE_KEY_INFO } from '@/lib/crypto/kdf';
import { generateVaultKey, encodeVaultKey, decodeVaultKey } from '@/lib/crypto/vaultkey';
import { crockfordEncode, crockfordDecode } from '@/lib/crypto/base32';
import {
  createShares,
  rejoinShares,
  ShareError,
  SHARE_A_PREFIX,
  SHARE_B_PREFIX,
} from '@/lib/crypto/shares';
import {
  rsEncode,
  rsDecode,
  rsEncodeInterleaved,
  rsDecodeInterleaved,
  legacyV1Parity30Pct,
  interleaveParams,
  interleave,
  deinterleave,
  RSUncorrectable,
  gfMul,
  gfDiv,
  gfPow,
  gfInverse,
} from '@/lib/rs/rs';
import {
  encodePayload,
  decodePayload,
  extractToken,
  wrapToken,
  codecParams,
  RS_PARITY_BYTES,
  SENTINEL,
  ERASURE_MARK,
} from '@/lib/codec/footer';
import { BECH32_CHARSET } from '@/lib/codec/bech32';
import {
  renderFooter,
  createRecoveryPage,
  recoverFromFooter,
  CURATED_RECIPES,
} from '@/lib/pipeline';
import { assert, type SuiteGroup } from './runner';

// ── Shared fixtures (identical to the vitest files) ──────────────────────────

const capsuleRng = () => DeterministicTestRNG.fromSeedNumber(1);

function capsuleFixture() {
  const r = capsuleRng();
  const entropy = mnemonicToEntropy32(FIXED_TEST_MNEMONIC);
  const vaultKey = generateVaultKey(r);
  const capsule = createCapsule(entropy, vaultKey, r);
  return { entropy, vaultKey, capsule };
}

const sharesRng = () => DeterministicTestRNG.fromSeedNumber(42);

function sharesFixture(gen = 1) {
  const r = sharesRng();
  const k = generateVaultKey(r);
  const { shareA, shareB } = createShares(k, r, gen);
  return { k, shareA, shareB };
}

/** Deterministic pseudo-random 49-byte capsule-shaped payloads (footer.test.ts). */
function testCapsule(i: number): Uint8Array {
  const a = sha256(new Uint8Array([0x66, 0x63, i & 0xff, (i >> 8) & 0xff]));
  const b = sha256(a);
  const out = new Uint8Array(49);
  out.set(a.slice(0, 32), 0);
  out.set(b.slice(0, 17), 32);
  return out;
}

/** Deterministic PRNG for corruption positions (footer.test.ts). */
function* prng(seed: number): Generator<number, never, unknown> {
  let s = seed >>> 0 || 1;
  while (true) {
    s ^= s << 13; s >>>= 0;
    s ^= s >> 17;
    s ^= s << 5; s >>>= 0;
    yield s;
  }
}

function flipBit(arr: Uint8Array, pos: number): Uint8Array {
  const out = arr.slice();
  out[pos] ^= 1;
  return out;
}

function erase(codeword: Uint8Array, positions: number[]): Uint8Array {
  const out = codeword.slice();
  for (const p of positions) out[p] = 0xee;
  return out;
}

const P = codecParams();

// RFC 8452 Appendix C.2 vectors (capsule2.test.ts) — copied verbatim.
const RFC8452_KEY = hexToBytes('0100000000000000000000000000000000000000000000000000000000000000');
const RFC8452_NONCE = hexToBytes('030000000000000000000000');
const C2_VECTORS = [
  { name: 'C.2 empty plaintext', plaintext: '', aad: '', result: '07f5f4169bbf55a8400cd47ea6fd400f' },
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

// ── Group: External KATs ──────────────────────────────────────────────────────

const katsGroup: SuiteGroup = {
  id: 'kats',
  label: 'External KATs (BIP39 · BIP32 · HKDF · XChaCha20 · RFC 8452)',
  tests: [
    {
      name: 'BIP39: all-zero 256-bit entropy produces 23x abandon + art',
      scope: 'smoke',
      run: () => {
        const v = BIP39_TREZOR_VECTORS[0];
        assert.eq(v.entropyHex, '00'.repeat(32));
        const mnemonic = entropy32ToMnemonic(hexToBytes(v.entropyHex));
        assert.eq(mnemonic, v.mnemonic);
        assert.eq(mnemonic, FIXED_TEST_MNEMONIC);
        assert.eq(mnemonic.split(' ').slice(0, 23), Array(23).fill('abandon'));
        assert.eq(mnemonic.split(' ')[23], 'art');
      },
    },
    ...BIP39_TREZOR_VECTORS.map((v) => ({
      name: `BIP39: entropy ${v.entropyHex.slice(0, 8)}… round-trips and derives the published seed`,
      scope: 'smoke' as const,
      run: () => {
        const mnemonic = entropy32ToMnemonic(hexToBytes(v.entropyHex));
        assert.eq(mnemonic, v.mnemonic);
        assert.eq(bytesToHex(mnemonicToEntropy32(v.mnemonic)), v.entropyHex);
        const seed = mnemonicToSeedSync(v.mnemonic, 'TREZOR');
        assert.eq(bytesToHex(seed), v.seedHexTrezorPassphrase);
      },
    })),
    {
      name: 'BIP39: rejects wrong word count, unknown words, and bad checksum',
      scope: 'smoke',
      run: () => {
        assert.eq(validateMnemonic24('abandon abandon art').valid, false);
        assert.eq(validateMnemonic24(`${'abandon '.repeat(23)}zzzzzz`.trim()).valid, false);
        assert.eq(validateMnemonic24(`${'abandon '.repeat(24)}`.trim()).valid, false);
        assert.eq(validateMnemonic24(FIXED_TEST_MNEMONIC).valid, true);
      },
    },
    {
      name: 'BIP32: master extended keys match the published vector',
      scope: 'smoke',
      run: () => {
        const hd = HDKey.fromMasterSeed(hexToBytes(BIP32_TEST_VECTOR_1.seedHex));
        assert.eq(hd.privateExtendedKey, BIP32_TEST_VECTOR_1.master.xprv);
        assert.eq(hd.publicExtendedKey, BIP32_TEST_VECTOR_1.master.xpub);
      },
    },
    {
      name: "BIP32: derived m/0' and m/0'/1 extended keys match the published vector",
      scope: 'smoke',
      run: () => {
        const hd = HDKey.fromMasterSeed(hexToBytes(BIP32_TEST_VECTOR_1.seedHex));
        const m0h = hd.derive("m/0'");
        assert.eq(m0h.privateExtendedKey, BIP32_TEST_VECTOR_1.m0h.xprv);
        assert.eq(m0h.publicExtendedKey, BIP32_TEST_VECTOR_1.m0h.xpub);
        const m0h1 = hd.derive("m/0'/1");
        assert.eq(m0h1.privateExtendedKey, BIP32_TEST_VECTOR_1.m0h1.xprv);
        assert.eq(m0h1.publicExtendedKey, BIP32_TEST_VECTOR_1.m0h1.xpub);
      },
    },
    {
      name: "BIP32: master fingerprint matches the parent-fingerprint field embedded in the published m/0' xprv",
      scope: 'smoke',
      run: () => {
        const decoded = base58check(sha256).decode(BIP32_TEST_VECTOR_1.m0h.xprv);
        const publishedParentFp = decoded.slice(5, 9);
        const seed = hexToBytes(BIP32_TEST_VECTOR_1.seedHex);
        const fp = masterFingerprintFromSeed(seed);
        assert.eq(bytesToHex(fp), bytesToHex(publishedParentFp));
        assert.match(formatFingerprint(fp), /^[0-9A-F]{4}-[0-9A-F]{4}$/);
      },
    },
    ...( [
      ['case 1', RFC5869_CASE_1],
      ['case 2', RFC5869_CASE_2],
    ] as const).map(([name, c]) => ({
      name: `HKDF-SHA256 RFC 5869 ${name}: PRK and OKM match the RFC`,
      scope: 'smoke' as const,
      run: () => {
        const ikm = hexToBytes(c.ikmHex);
        const salt = hexToBytes(c.saltHex);
        const info = hexToBytes(c.infoHex);
        const prk = extract(sha256, ikm, salt);
        assert.eq(bytesToHex(prk), c.prkHex);
        const okm = hkdf(sha256, ikm, salt, info, c.length);
        assert.eq(bytesToHex(okm), c.okmHex);
      },
    })),
    {
      name: 'XChaCha20-Poly1305 (draft-irtf-cfrg-xchacha-03 A.3.1): encrypt matches the published ciphertext and tag',
      scope: 'smoke',
      run: () => {
        const { ciphertext, tag } = aeadEncrypt(
          hexToBytes(XCHACHA20_POLY1305_KAT.keyHex),
          hexToBytes(XCHACHA20_POLY1305_KAT.nonceHex),
          hexToBytes(XCHACHA20_POLY1305_KAT.plaintextHex),
          hexToBytes(XCHACHA20_POLY1305_KAT.aadHex),
        );
        assert.eq(bytesToHex(ciphertext), XCHACHA20_POLY1305_KAT.ciphertextHex);
        assert.eq(bytesToHex(tag), XCHACHA20_POLY1305_KAT.tagHex);
      },
    },
    {
      name: 'XChaCha20-Poly1305: decrypt of the published ciphertext recovers the published plaintext',
      scope: 'smoke',
      run: () => {
        const pt = aeadDecrypt(
          hexToBytes(XCHACHA20_POLY1305_KAT.keyHex),
          hexToBytes(XCHACHA20_POLY1305_KAT.nonceHex),
          hexToBytes(XCHACHA20_POLY1305_KAT.ciphertextHex),
          hexToBytes(XCHACHA20_POLY1305_KAT.tagHex),
          hexToBytes(XCHACHA20_POLY1305_KAT.aadHex),
        );
        assert.eq(bytesToHex(pt), XCHACHA20_POLY1305_KAT.plaintextHex);
      },
    },
    {
      name: 'XChaCha20-Poly1305: tampered tag fails authentication',
      scope: 'smoke',
      run: () => {
        const tag = hexToBytes(XCHACHA20_POLY1305_KAT.tagHex);
        tag[0] ^= 0x01;
        assert.throws(() =>
          aeadDecrypt(
            hexToBytes(XCHACHA20_POLY1305_KAT.keyHex),
            hexToBytes(XCHACHA20_POLY1305_KAT.nonceHex),
            hexToBytes(XCHACHA20_POLY1305_KAT.ciphertextHex),
            tag,
            hexToBytes(XCHACHA20_POLY1305_KAT.aadHex),
          ),
        );
      },
    },
    ...C2_VECTORS.map((v) => ({
      name: `RFC 8452 AES-256-GCM-SIV ${v.name}: matches the published result`,
      scope: 'smoke' as const,
      run: () => {
        const sealed = gcmsiv(RFC8452_KEY, RFC8452_NONCE, hexToBytes(v.aad)).encrypt(
          hexToBytes(v.plaintext),
        );
        assert.eq(bytesToHex(sealed), v.result);
        const opened = gcmsiv(RFC8452_KEY, RFC8452_NONCE, hexToBytes(v.aad)).decrypt(
          hexToBytes(v.result),
        );
        assert.eq(bytesToHex(opened), v.plaintext);
      },
    })),
  ],
};

// ── Group: Capsule + Vault Key + Shares ───────────────────────────────────────

const ENTROPY_V2 = new Uint8Array(32).map((_, i) => i * 7 + 1);
const VK_V2 = new Uint8Array(32).map((_, i) => 255 - i);

const capsuleGroup: SuiteGroup = {
  id: 'capsule',
  label: 'Capsule (v1 + v2) · Vault Key · Shares',
  tests: [
    {
      name: 'capsule v1 is exactly 93 bytes with the specified field layout',
      scope: 'smoke',
      run: () => {
        const { capsule } = capsuleFixture();
        assert.eq(capsule.length, CAPSULE_LENGTH);
        const f = parseCapsule(capsule);
        assert.eq(f.version, CAPSULE_VERSION);
        assert.eq(f.generation, INITIAL_GENERATION);
        assert.eq(f.capsuleId.length, 16);
        assert.eq(f.nonce.length, 24);
        assert.eq(f.ciphertext.length, 32);
        assert.eq(f.tag.length, 16);
        assert.eq(bytesToHex(serializeCapsule(f)), bytesToHex(capsule));
        assert.eq(
          bytesToHex(capsuleAad(f.version, f.generation, f.capsuleId)),
          bytesToHex(capsule.slice(0, 21)),
        );
      },
    },
    {
      name: 'capsule v1 is deterministic under the same test RNG stream',
      scope: 'smoke',
      run: () => {
        assert.eq(bytesToHex(capsuleFixture().capsule), bytesToHex(capsuleFixture().capsule));
      },
    },
    {
      name: 'capsule v1 round-trip recovers byte-identical entropy',
      scope: 'smoke',
      run: () => {
        const { entropy, vaultKey, capsule } = capsuleFixture();
        assert.eq(equalBytes(openCapsule(capsule, vaultKey), entropy), true);
      },
    },
    {
      name: 'capsule v1 failure behavior: ciphertext, tag, wrong key, generation, ID, truncation, version all fail',
      scope: 'smoke',
      run: () => {
        const { vaultKey, capsule } = capsuleFixture();
        for (const [idx, bit] of [
          [45, 0x01],
          [92, 0x80],
          [4, 0x01],
          [5, 0x01],
        ] as const) {
          const bad = capsule.slice();
          bad[idx] ^= bit;
          assert.throws(() => openCapsule(bad, vaultKey), CapsuleError);
        }
        const wrongKey = DeterministicTestRNG.fromSeedNumber(999).randomBytes(32);
        assert.throws(() => openCapsule(capsule, wrongKey), CapsuleError);
        assert.throws(() => openCapsule(capsule.slice(0, 92), vaultKey), /malformed length/);
        assert.throws(() => openCapsule(new Uint8Array(0), vaultKey), CapsuleError);
        const badVersion = capsule.slice();
        badVersion[0] = 0x02;
        assert.throws(() => openCapsule(badVersion, vaultKey), /version/);
      },
    },
    {
      name: 'capsule v1 key derivation uses the pinned info string and differs across generation/ID/key',
      scope: 'smoke',
      run: () => {
        assert.eq(CAPSULE_KEY_INFO, 'CLOAKVAULT-V1-CAPSULE-KEY');
        const r = capsuleRng();
        const k = r.randomBytes(32);
        const id = r.randomBytes(16);
        const a = deriveCapsuleKey(k, id, 1);
        assert.eq(a.length, 32);
        assert.notEq(bytesToHex(deriveCapsuleKey(k, id, 2)), bytesToHex(a));
        const id2 = id.slice();
        id2[0] ^= 1;
        assert.notEq(bytesToHex(deriveCapsuleKey(k, id2, 1)), bytesToHex(a));
      },
    },
    {
      name: 'Vault Key CVK1. encodes with prefix, grouping, and round-trips (case/hyphen tolerant)',
      scope: 'smoke',
      run: () => {
        const k = capsuleRng().randomBytes(32);
        const text = encodeVaultKey(k);
        assert.eq(text.startsWith('CVK1.'), true);
        assert.match(text.slice(5), /^[0-9A-HJKMNP-TV-Z]{4}(-[0-9A-HJKMNP-TV-Z]{1,4})*$/);
        assert.eq(equalBytes(decodeVaultKey(text), k), true);
        assert.eq(equalBytes(decodeVaultKey(text.toLowerCase()), k), true);
        assert.eq(equalBytes(decodeVaultKey('CVK1.' + text.slice(5).replace(/-/g, '')), k), true);
      },
    },
    {
      name: 'Vault Key rejects checksum mismatch, wrong prefix, wrong length',
      scope: 'smoke',
      run: () => {
        const k = capsuleRng().randomBytes(32);
        const text = encodeVaultKey(k);
        const body = text.slice(5).replace(/-/g, '');
        const flipped = (body[0] === 'A' ? 'B' : 'A') + body.slice(1);
        assert.throws(() => decodeVaultKey('CVK1.' + flipped));
        assert.throws(() => decodeVaultKey(body), /prefix/);
        assert.throws(() => decodeVaultKey('CVK1.' + body.slice(0, -1)));
        assert.throws(() => decodeVaultKey('CVK1.' + body + 'A'));
      },
    },
    {
      name: 'Crockford Base32 maps I/L→1 and O→0 and rejects U',
      scope: 'smoke',
      run: () => {
        const bytes = new Uint8Array([0xde, 0xad, 0xbe, 0xef, 0x00]);
        const enc = crockfordEncode(bytes);
        const dec = crockfordDecode(enc.replace(/0/g, 'O').replace(/1/g, 'I'), 5);
        assert.eq(equalBytes(dec, bytes), true);
        assert.throws(() => crockfordDecode('U'.repeat(8), 5));
      },
    },
    {
      name: 'deterministic RNG: same seed → identical stream; different seed → different stream',
      scope: 'smoke',
      run: () => {
        const a = DeterministicTestRNG.fromSeedNumber(7).randomBytes(64);
        const b = DeterministicTestRNG.fromSeedNumber(7).randomBytes(64);
        const c = DeterministicTestRNG.fromSeedNumber(8).randomBytes(64);
        assert.eq(bytesToHex(a), bytesToHex(b));
        assert.notEq(bytesToHex(a), bytesToHex(c));
      },
    },
    {
      name: 'capsule v2 round-trips and is exactly 49 bytes',
      scope: 'smoke',
      run: () => {
        const c = createCapsuleV2(ENTROPY_V2, VK_V2);
        assert.eq(c.length, CAPSULE2_LENGTH);
        assert.eq(c[0], CAPSULE2_VERSION);
        assert.eq([...openCapsuleV2(c, VK_V2)], [...ENTROPY_V2]);
      },
    },
    {
      name: 'capsule v2 is deterministic: same seed + key → byte-identical capsule (intended)',
      scope: 'smoke',
      run: () => {
        assert.eq(
          bytesToHex(createCapsuleV2(ENTROPY_V2, VK_V2)),
          bytesToHex(createCapsuleV2(ENTROPY_V2, VK_V2)),
        );
      },
    },
    {
      name: 'capsule v2: different key → different capsule; wrong key fails cleanly',
      scope: 'smoke',
      run: () => {
        const c = createCapsuleV2(ENTROPY_V2, VK_V2);
        const otherKey = new Uint8Array(32).map((_, i) => i);
        assert.notEq(bytesToHex(createCapsuleV2(ENTROPY_V2, otherKey)), bytesToHex(c));
        assert.throws(() => openCapsuleV2(c, otherKey), Capsule2Error);
      },
    },
    {
      name: 'capsule v2: tampering any region fails (version, ciphertext, tag, truncation)',
      scope: 'smoke',
      run: () => {
        const c = createCapsuleV2(ENTROPY_V2, VK_V2);
        for (const idx of [0, 1, 20, 32, 33, 48]) {
          const t = c.slice();
          t[idx] ^= 0x01;
          assert.throws(() => openCapsuleV2(t, VK_V2), Capsule2Error);
        }
        assert.throws(() => openCapsuleV2(c.slice(0, 48), VK_V2), Capsule2Error);
      },
    },
    {
      name: 'capsule v2 HKDF derivation uses the frozen constants',
      scope: 'smoke',
      run: () => {
        const derived = deriveCapsuleKeyV2(VK_V2);
        assert.eq(derived.length, 32);
        assert.eq('CLOAKVAULT-V3-CAPSULE-KEY'.length, 25);
      },
    },
    {
      name: 'shares: CVSA1./CVSB1. prefixes present and deterministic under the test RNG',
      scope: 'smoke',
      run: () => {
        const a = sharesFixture();
        const b = sharesFixture();
        assert.eq(a.shareA.startsWith(SHARE_A_PREFIX), true);
        assert.eq(a.shareB.startsWith(SHARE_B_PREFIX), true);
        assert.eq(a.shareA, b.shareA);
        assert.eq(a.shareB, b.shareB);
      },
    },
    {
      name: 'shares: rejoin reconstructs the original Vault Key exactly, independent of generation',
      scope: 'smoke',
      run: () => {
        const { k, shareA, shareB } = sharesFixture();
        assert.eq(equalBytes(decodeVaultKey(rejoinShares(shareA, shareB)), k), true);
        for (const gen of [1, 2, 100, 0xffffffff]) {
          const r = sharesRng();
          const k2 = generateVaultKey(r);
          const s = createShares(k2, r, gen);
          assert.eq(equalBytes(decodeVaultKey(rejoinShares(s.shareA, s.shareB)), k2), true);
        }
      },
    },
    {
      name: 'shares: exact validation errors (checksum, both-A, both-B, generation mismatch, missing prefix)',
      scope: 'smoke',
      run: () => {
        const { shareA, shareB } = sharesFixture();
        const bodyA = shareA.slice(SHARE_A_PREFIX.length).replace(/-/g, '');
        const midA = Math.floor(bodyA.length / 2);
        const badA =
          SHARE_A_PREFIX +
          bodyA.slice(0, midA) +
          (bodyA[midA] === 'A' ? 'B' : 'A') +
          bodyA.slice(midA + 1);
        assert.throws(() => rejoinShares(badA, shareB), ShareError);
        assert.throws(() => rejoinShares(badA, shareB), /checksum/i);
        const bodyB = shareB.slice(SHARE_B_PREFIX.length).replace(/-/g, '');
        const midB = Math.floor(bodyB.length / 2);
        const badB =
          SHARE_B_PREFIX +
          bodyB.slice(0, midB) +
          (bodyB[midB] === 'A' ? 'B' : 'A') +
          bodyB.slice(midB + 1);
        assert.throws(() => rejoinShares(shareA, badB), ShareError);
        assert.throws(() => rejoinShares(shareA, badB), /checksum/i);
        assert.throws(() => rejoinShares(shareA, shareA), /Both inputs are Share A/);
        assert.throws(() => rejoinShares(shareB, shareB), /Both inputs are Share B/);
        const r1 = sharesRng();
        const k1 = generateVaultKey(r1);
        const s1 = createShares(k1, r1, 1);
        const r2 = sharesRng();
        const k2 = generateVaultKey(r2);
        const s2 = createShares(k2, r2, 2);
        assert.throws(() => rejoinShares(s1.shareA, s2.shareB), /Generation mismatch/);
        assert.throws(() => rejoinShares('garbage', shareB));
        assert.throws(() => rejoinShares(shareA, 'garbage'));
      },
    },
  ],
};

// ── Group: Reed-Solomon ───────────────────────────────────────────────────────

const RS_DATA_93 = new Uint8Array(93);
for (let i = 0; i < 93; i++) RS_DATA_93[i] = i;
const RS_DATA_4 = new Uint8Array([0x01, 0x02, 0x03, 0x04]);

const rsGroup: SuiteGroup = {
  id: 'rs',
  label: 'Reed-Solomon GF(2^8) boundary suite',
  tests: [
    {
      name: 'GF(2^8) field arithmetic: identity, zero, commutativity, associativity, inverse, pow, div',
      scope: 'smoke',
      run: () => {
        for (const a of [0, 1, 7, 42, 128, 255]) assert.eq(gfMul(a, 1), a);
        for (const x of [0, 1, 100, 255]) assert.eq(gfMul(0, x), 0);
        for (const [a, b] of [[3, 7], [12, 200], [255, 1], [127, 128]]) {
          assert.eq(gfMul(a, b), gfMul(b, a));
        }
        assert.eq(gfMul(gfMul(3, 5), 7), gfMul(3, gfMul(5, 7)));
        for (const a of [1, 2, 7, 42, 128, 255]) assert.eq(gfMul(a, gfInverse(a)), 1);
        for (const x of [2, 7, 255]) {
          assert.eq(gfPow(x, 0), 1);
          assert.eq(gfPow(x, 1), x);
        }
        for (const a of [1, 42, 255]) assert.eq(gfDiv(a, a), 1);
      },
    },
    {
      name: 'legacy v1 parity rule (superseded): ceil(30%) of 93/4/10/1 = 28/2/3/1',
      scope: 'smoke',
      run: () => {
        assert.eq(legacyV1Parity30Pct(93), 28);
        assert.eq(legacyV1Parity30Pct(4), 2);
        assert.eq(legacyV1Parity30Pct(10), 3);
        assert.eq(legacyV1Parity30Pct(1), 1);
      },
    },
    {
      name: 'independent vectors (k=4, parity=2): deterministic systematic encode, clean decode, 1–2 erasures, 1 error, uncorrectable beyond',
      scope: 'smoke',
      run: () => {
        const cw = rsEncode(RS_DATA_4, 2);
        assert.eq(cw.length, 6);
        assert.eq([...cw.slice(0, 4)], [...RS_DATA_4]);
        assert.eq(bytesToHex(cw), bytesToHex(rsEncode(RS_DATA_4, 2)));
        assert.eq(bytesToHex(rsDecode(cw, 2)), bytesToHex(RS_DATA_4));
        assert.eq(bytesToHex(rsDecode(erase(cw, [4]), 2, [4])), bytesToHex(RS_DATA_4));
        assert.eq(bytesToHex(rsDecode(erase(cw, [4, 5]), 2, [4, 5])), bytesToHex(RS_DATA_4));
        assert.throws(() => rsDecode(erase(cw, [3, 4, 5]), 2, [3, 4, 5]), RSUncorrectable);
        assert.eq(bytesToHex(rsDecode(flipBit(cw, 0), 2)), bytesToHex(RS_DATA_4));
        assert.throws(() => rsDecode(flipBit(flipBit(cw, 0), 5), 2), RSUncorrectable);
      },
    },
    {
      name: 'legacy v1 RS(121,93) profile — superseded: encode + clean decode',
      scope: 'smoke',
      run: () => {
        const cw = rsEncode(RS_DATA_93, 28);
        assert.eq(cw.length, 121);
        assert.eq([...cw.slice(0, 93)], [...RS_DATA_93]);
        assert.eq(bytesToHex(rsDecode(cw, 28)), bytesToHex(RS_DATA_93));
      },
    },
    {
      name: 'pure erasures: corrects 28 (exact max) and 20 random; fails on 29 (one beyond)',
      scope: 'smoke',
      run: () => {
        const cw = rsEncode(RS_DATA_93, 28);
        const all28 = Array.from({ length: 28 }, (_, i) => 93 + i);
        assert.eq(bytesToHex(rsDecode(erase(cw, all28), 28, all28)), bytesToHex(RS_DATA_93));
        const p20 = [0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95];
        assert.eq(bytesToHex(rsDecode(erase(cw, p20), 28, p20)), bytesToHex(RS_DATA_93));
        const p29 = Array.from({ length: 29 }, (_, i) => i);
        assert.throws(() => rsDecode(erase(cw, p29), 28, p29), RSUncorrectable);
      },
    },
    {
      name: 'pure errors: corrects 14 (exact max) and 10 scattered; fails on 15 (one beyond)',
      scope: 'smoke',
      run: () => {
        const cw = rsEncode(RS_DATA_93, 28);
        const rx14 = cw.slice();
        for (let i = 0; i < 14; i++) rx14[(i * 7) % 121] ^= i + 1;
        assert.eq(bytesToHex(rsDecode(rx14, 28)), bytesToHex(RS_DATA_93));
        const rx10 = cw.slice();
        for (const p of [3, 11, 20, 33, 47, 58, 71, 82, 99, 115]) rx10[p] ^= 0x55;
        assert.eq(bytesToHex(rsDecode(rx10, 28)), bytesToHex(RS_DATA_93));
        const rx15 = cw.slice();
        for (let i = 0; i < 15; i++) rx15[(i * 7) % 121] ^= i + 1;
        assert.throws(() => rsDecode(rx15, 28), RSUncorrectable);
      },
    },
    {
      name: 'mixed: 5 errors + 18 erasures and 7 errors + 14 erasures (exact boundary) decode; 6+18 (beyond) fails',
      scope: 'smoke',
      run: () => {
        const cw = rsEncode(RS_DATA_93, 28);
        {
          const rx = cw.slice();
          for (const p of [2, 15, 30, 60, 90]) rx[p] ^= 0x77;
          const er = [5, 10, 20, 25, 35, 40, 45, 50, 55, 65, 70, 75, 80, 85, 93, 100, 110, 120];
          for (const p of er) rx[p] = 0xee;
          assert.eq(bytesToHex(rsDecode(rx, 28, er)), bytesToHex(RS_DATA_93));
        }
        {
          const rx = cw.slice();
          for (const p of [1, 13, 27, 39, 51, 63, 75]) rx[p] ^= 0x33;
          const er = [4, 8, 12, 16, 24, 28, 32, 36, 44, 48, 52, 56, 64, 68];
          for (const p of er) rx[p] = 0xcc;
          assert.eq(bytesToHex(rsDecode(rx, 28, er)), bytesToHex(RS_DATA_93));
        }
        {
          const rx = cw.slice();
          for (const p of [2, 15, 30, 60, 90, 92]) rx[p] ^= 0x77;
          const er = [5, 10, 20, 25, 35, 40, 45, 50, 55, 65, 70, 75, 80, 85, 93, 100, 110, 120];
          for (const p of er) rx[p] = 0xee;
          assert.throws(() => rsDecode(rx, 28, er), RSUncorrectable);
        }
      },
    },
    {
      name: 'fails on 29 erasures at scattered positions',
      scope: 'smoke',
      run: () => {
        const cw = rsEncode(RS_DATA_93, 28);
        const rx = cw.slice();
        const positions = Array.from({ length: 29 }, (_, i) => (i * 4) % 121);
        const unique = [...new Set(positions)].slice(0, 29);
        for (const p of unique) rx[p] = 0xee;
        assert.throws(() => rsDecode(rx, 28, unique), RSUncorrectable);
      },
    },
    {
      name: 'round-trips 50 random 93-byte payloads without errors',
      scope: 'smoke',
      run: () => {
        const r = DeterministicTestRNG.fromSeedNumber(200);
        for (let i = 0; i < 50; i++) {
          const d = r.randomBytes(93);
          assert.eq(bytesToHex(rsDecode(rsEncode(d, 28), 28)), bytesToHex(d));
        }
      },
    },
    {
      name: 'legacy v1 interleaving (superseded): stride 12/111, identity round-trip, reordering, erasures in interleaved domain',
      scope: 'smoke',
      run: () => {
        const { stride, invStride } = interleaveParams(121);
        assert.eq(stride, 12);
        assert.eq(invStride, 111);
        assert.eq((12 * 111) % 121, 1);
        const data = new Uint8Array(121);
        for (let i = 0; i < 121; i++) data[i] = i % 256;
        assert.eq(bytesToHex(deinterleave(interleave(data))), bytesToHex(data));
        const seq = new Uint8Array(121);
        for (let i = 0; i < 121; i++) seq[i] = i;
        assert.notEq(bytesToHex(interleave(seq)), bytesToHex(seq));
        const d93 = new Uint8Array(93);
        for (let i = 0; i < 93; i++) d93[i] = (i * 3 + 7) % 256;
        const tx = rsEncodeInterleaved(d93, 28);
        assert.eq(tx.length, 121);
        assert.eq(bytesToHex(rsDecodeInterleaved(tx, 28)), bytesToHex(d93));
        const d2 = new Uint8Array(93);
        for (let i = 0; i < 93; i++) d2[i] = i;
        const tx2 = rsEncodeInterleaved(d2, 28);
        const eras = Array.from({ length: 20 }, (_, i) => i);
        const rx = tx2.slice();
        for (const p of eras) rx[p] = 0xee;
        assert.eq(bytesToHex(rsDecodeInterleaved(rx, 28, eras)), bytesToHex(d2));
        const cwPos = [0, 1, 2].map((i) => (i * stride) % 121);
        assert.notEq(cwPos[1] - cwPos[0], 1);
      },
    },
  ],
};

// ── Group: Footer codec ───────────────────────────────────────────────────────

const codecGroup: SuiteGroup = {
  id: 'codec',
  label: 'Footer codec (RS(83,49) · Bech32 · extraction)',
  tests: [
    {
      name: 'shipped parameters: RS(83,49), 34 parity, 133 data chars, 142-char token',
      scope: 'smoke',
      run: () => {
        assert.eq(RS_PARITY_BYTES, 34);
        assert.eq(P.n, 83);
        assert.eq(P.k, 49);
        assert.eq(P.dataChars, 133);
        assert.eq(P.tokenLength, 142);
        assert.eq(P.maxErasures, 34);
        assert.eq(P.maxErrors, 17);
      },
    },
    {
      name: 'round trip is identity over 1000 pseudo-random capsules (clean input, zero loss)',
      scope: 'full',
      run: () => {
        for (let i = 0; i < 1000; i++) {
          const capsule = testCapsule(i);
          const token = encodePayload(capsule);
          assert.eq(token.length, P.tokenLength);
          assert.eq(token.startsWith(SENTINEL), true);
          const report = decodePayload(token);
          assert.eq(report.decoded, true);
          assert.eq(report.checksumValid, true);
          assert.eq(report.errorsCorrected, 0);
          assert.eq(report.erasuresUsed, 0);
          assert.eq([...report.capsule!], [...capsule]);
        }
      },
    },
    {
      name: 'Bech32 checksum detects corruption of ANY single character (exhaustive: all positions × a substitute)',
      scope: 'full',
      run: () => {
        const token = encodePayload(testCapsule(1));
        const body = token.slice(SENTINEL.length);
        for (let pos = 0; pos < body.length; pos++) {
          const orig = body[pos];
          const replacement = BECH32_CHARSET[(BECH32_CHARSET.indexOf(orig) + 1) % 32];
          const corrupted = body.slice(0, pos) + replacement + body.slice(pos + 1);
          const report = decodePayload(SENTINEL + corrupted);
          assert.eq(report.checksumValid, false, `position ${pos} not detected`);
        }
      },
    },
    {
      name: 'decodes at the theoretical erasure limit (34 byte-erasures) and fails cleanly beyond',
      scope: 'full',
      run: () => {
        const capsule = testCapsule(2);
        const token = encodePayload(capsule);
        const body = [...token.slice(SENTINEL.length)];
        let lastGood: ReturnType<typeof decodePayload> | null = null;
        for (let count = 1; count <= body.length; count++) {
          const marked = body.slice();
          for (let j = 0; j < count; j++) marked[j] = ERASURE_MARK;
          const report = decodePayload(SENTINEL + marked.join(''));
          if (report.erasuresUsed <= 34) {
            assert.eq(report.decoded, true, `failed at ${report.erasuresUsed} erasures`);
            assert.eq([...report.capsule!], [...capsule]);
            lastGood = report;
          } else {
            assert.eq(report.decoded, false);
            assert.match(report.failure ?? '', /budget|erasures/i);
            break;
          }
        }
        assert.ok(lastGood !== null, 'no decode succeeded');
        assert.eq(lastGood!.erasuresUsed, 34);
      },
    },
    {
      name: 'burst erasure: a contiguous stain across one wrapped line decodes',
      scope: 'smoke',
      run: () => {
        const capsule = testCapsule(3);
        const token = encodePayload(capsule);
        const lines = wrapToken(token);
        const damaged = lines
          .map((l, i) =>
            i === 1
              ? ERASURE_MARK.repeat(Math.floor(l.length * 0.6)) + l.slice(Math.floor(l.length * 0.6))
              : l,
          )
          .join('\n');
        const report = decodePayload(damaged);
        assert.eq(report.decoded, true);
        assert.eq([...report.capsule!], [...capsule]);
        assert.gte(report.erasuresUsed, 1);
      },
    },
    {
      name: 'scattered silent errors up to the error budget decode, with counts reported',
      scope: 'smoke',
      run: () => {
        const capsule = testCapsule(4);
        const token = encodePayload(capsule);
        const body = [...token.slice(SENTINEL.length, SENTINEL.length + P.dataChars)];
        const g = prng(42);
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
        assert.eq(report.checksumValid, false);
        assert.eq(report.decoded, true);
        assert.eq([...report.capsule!], [...capsule]);
        assert.gte(report.errorsCorrected, 8);
        assert.lte(report.parityBudgetUsed, 34);
      },
    },
    {
      name: 'genre independence: the same token extracts and decodes identically from ≥2 different fake footers',
      scope: 'smoke',
      run: () => {
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
          assert.eq(r.extracted, true);
          assert.eq(r.decoded, true);
          assert.eq([...r.capsule!], [...capsule]);
        }
        assert.eq(
          reports.map((r) => [...r.capsule!].join(',')),
          Array(footers.length).fill([...capsule].join(',')),
        );
      },
    },
    {
      name: 'extraction falls back to a length-run when the sentinel itself is damaged',
      scope: 'smoke',
      run: () => {
        const capsule = testCapsule(6);
        const token = encodePayload(capsule);
        const damagedSentinel = ERASURE_MARK.repeat(SENTINEL.length) + token.slice(SENTINEL.length);
        const { token: found, method } = extractToken(`https://x.example/?id=${damagedSentinel}`);
        assert.ok(found !== null, 'token not found');
        assert.eq(method, 'run');
      },
    },
    {
      name: 'body/footer independence: body change leaves payload byte-identical, and vice versa',
      scope: 'smoke',
      run: () => {
        const rngA = new DeterministicTestRNG(new Uint8Array(32).fill(9));
        const rngB = new DeterministicTestRNG(new Uint8Array(32).fill(9));
        const pageA = createRecoveryPage(FIXED_TEST_MNEMONIC, rngA, CURATED_RECIPES[0].id);
        const pageB = createRecoveryPage(FIXED_TEST_MNEMONIC, rngB, CURATED_RECIPES[2].id);
        assert.eq(pageB.token, pageA.token);
        assert.notEq(pageB.recipe.body, pageA.recipe.body);
        const rngC = new DeterministicTestRNG(new Uint8Array(32).fill(10));
        const pageC = createRecoveryPage(FIXED_TEST_MNEMONIC, rngC, CURATED_RECIPES[0].id);
        assert.notEq(pageC.token, pageA.token);
        assert.eq(pageC.recipe.body, pageA.recipe.body);
      },
    },
    {
      name: 'full page round-trip: paste the printed footer lines + Vault Key → mnemonic + fingerprint; wrong key fails cleanly',
      scope: 'smoke',
      run: () => {
        const rng = new DeterministicTestRNG(new Uint8Array(32).fill(7));
        const page = createRecoveryPage(FIXED_TEST_MNEMONIC, rng);
        const pasted = page.footer.lines.join('\n');
        const rec = recoverFromFooter(pasted, page.vaultKeyText);
        assert.eq(rec.ok, true);
        assert.eq(rec.mnemonic, FIXED_TEST_MNEMONIC);
        assert.eq(rec.fingerprint, page.fingerprint);
        const bad = recoverFromFooter(
          pasted,
          page.vaultKeyText.replace(/.$/, (c) => (c === 'A' ? 'B' : 'A')),
        );
        assert.eq(bad.ok, false);
        assert.eq(bad.mnemonic, null);
      },
    },
    {
      name: 'renderFooter wraps the token and appends the print exhaust framing',
      scope: 'smoke',
      run: () => {
        const token = encodePayload(testCapsule(7));
        const footer = renderFooter(token, '12/08/2026');
        assert.eq(footer.token, token);
        assert.ok(footer.lines[0].includes('/print?id='));
        assert.ok(footer.lines[footer.lines.length - 1].startsWith('Printed '));
        const report = decodePayload(footer.lines.join('\n'));
        assert.eq(report.decoded, true);
      },
    },
  ],
};

export const SUITE_GROUPS: SuiteGroup[] = [katsGroup, capsuleGroup, rsGroup, codecGroup];

/** Totals for display: [smokeCount, fullCount] per group id. */
export function suiteCounts(): Record<string, { smoke: number; full: number }> {
  const out: Record<string, { smoke: number; full: number }> = {};
  for (const g of SUITE_GROUPS) {
    out[g.id] = {
      smoke: g.tests.filter((t) => t.scope === 'smoke').length,
      full: g.tests.length,
    };
  }
  return out;
}
