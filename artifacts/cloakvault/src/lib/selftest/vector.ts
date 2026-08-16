/**
 * In-browser regeneration of the FROZEN conformance test vector,
 * docs/cloakvault-v3-test-vector.json.
 *
 * This mirrors the recomputation performed by scripts/verify-spec-vector.ts
 * (the read-only frozen-vector verifier). The regenerated JSON
 * string must byte-match the frozen file, which is imported raw at build
 * time. Export refuses to produce output unless the byte-match holds.
 */
import { bytesToHex, hexToBytes } from '@/lib/crypto/bytes';
import { entropy32ToMnemonic, mnemonicToBip39Seed } from '@/lib/crypto/wallet';
import { masterFingerprintFromSeed, formatFingerprint } from '@/lib/crypto/fingerprint';
import { encodeVaultKey } from '@/lib/crypto/vaultkey';
import {
  deriveCapsuleKeyV2,
  createCapsuleV2,
  openCapsuleV2,
  CAPSULE2_KEY_INFO,
} from '@/lib/crypto/capsule2';
import { rsEncode } from '@/lib/rs/rs';
import {
  encodePayload,
  decodePayload,
  RS_PARITY_BYTES,
  SENTINEL,
} from '@/lib/codec/footer';
import { renderFooter } from '@/lib/pipeline';

// The frozen, spec-authoritative vector file, byte-for-byte as committed.
import frozenVectorRaw from '../../../docs/cloakvault-v3-test-vector.json?raw';

export { frozenVectorRaw };

/** Recompute the vector object in memory (same fields scripts/verify-spec-vector.ts checks). */
export function regenerateVector(): { json: string; selfCheckOk: boolean } {
  // Fixed inputs (test secrets, published on purpose) — identical to the script.
  const SEED_ENTROPY = hexToBytes(
    '000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f',
  );
  const VAULT_KEY = hexToBytes(
    '202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f',
  );

  const mnemonic = entropy32ToMnemonic(SEED_ENTROPY);
  const bip39Seed = mnemonicToBip39Seed(mnemonic);
  const fingerprint = formatFingerprint(masterFingerprintFromSeed(bip39Seed));
  const vaultKeyText = encodeVaultKey(VAULT_KEY);
  const derivedKey = deriveCapsuleKeyV2(VAULT_KEY);
  const capsule = createCapsuleV2(SEED_ENTROPY, VAULT_KEY);
  const codeword = rsEncode(capsule, RS_PARITY_BYTES);
  const token = encodePayload(capsule);
  const footer = renderFooter(token, '12/08/2026');

  // Self-check: full decode path reproduces the inputs.
  const report = decodePayload(footer.lines.join('\n'));
  const selfCheckOk =
    report.decoded &&
    bytesToHex(report.capsule!) === bytesToHex(capsule) &&
    bytesToHex(openCapsuleV2(capsule, VAULT_KEY)) === bytesToHex(SEED_ENTROPY);

  const vector = {
    _warning:
      'TEST SECRETS ONLY. Published deliberately for interoperability testing. Never reuse.',
    protocolVersion: '0x02',
    description:
      'CloakVault v3 end-to-end conformance vector. Every intermediate value is produced by the reference implementation.',
    inputs: {
      seedEntropyHex: bytesToHex(SEED_ENTROPY),
      mnemonic,
      vaultKeyHex: bytesToHex(VAULT_KEY),
      vaultKeyText,
    },
    hkdf: {
      ikm: 'vaultKeyHex',
      saltHex: '',
      infoAscii: CAPSULE2_KEY_INFO,
      infoHex: bytesToHex(new TextEncoder().encode(CAPSULE2_KEY_INFO)),
      outputLength: 32,
      derivedCapsuleKeyHex: bytesToHex(derivedKey),
    },
    capsule: {
      lengthBytes: 49,
      versionByte: '0x02',
      aadHex: '02',
      nonceHex: '000000000000000000000000',
      capsuleHex: bytesToHex(capsule),
      ciphertextHex: bytesToHex(capsule.slice(1, 33)),
      tagHex: bytesToHex(capsule.slice(33)),
    },
    reedSolomon: {
      n: 83,
      k: 49,
      parity: RS_PARITY_BYTES,
      primitivePolynomial: '0x11d',
      generatorRoots: 'alpha^0 .. alpha^33',
      systematic:
        'codeword = data(49) || parity(34), parity highest-degree remainder coefficient first',
      codewordHex: bytesToHex(codeword),
      parityHex: bytesToHex(codeword.slice(49)),
    },
    bech32: {
      charset: 'qpzry9x8gf2tvdw0s3jn54khce6mua7l',
      hrp: 'cv',
      sentinel: SENTINEL,
      dataChars: 133,
      checksumChars: 6,
      tokenLength: token.length,
      token,
    },
    rendering: {
      wrapWidth: 48,
      note: 'Line wrapping is presentation-only; decoders strip all whitespace.',
      footerLines: footer.lines,
    },
    expectedRecovery: {
      fingerprint,
      mnemonic,
    },
  };

  return { json: JSON.stringify(vector, null, 2) + '\n', selfCheckOk };
}

export interface VectorCheck {
  selfCheckOk: boolean;
  byteMatch: boolean;
  regenerated: string;
  frozenLength: number;
  regeneratedLength: number;
}

/** Regenerate and compare against the frozen file, byte for byte. */
export function checkVectorByteMatch(): VectorCheck {
  const { json, selfCheckOk } = regenerateVector();
  return {
    selfCheckOk,
    byteMatch: json === frozenVectorRaw,
    regenerated: json,
    frozenLength: frozenVectorRaw.length,
    regeneratedLength: json.length,
  };
}
