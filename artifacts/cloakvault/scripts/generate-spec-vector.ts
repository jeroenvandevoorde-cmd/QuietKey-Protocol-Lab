/**
 * Regenerates the CloakVault v3 conformance test vector from the REAL
 * implementation, so the spec and code cannot silently diverge.
 *
 * Run: cd artifacts/cloakvault && npx tsx scripts/generate-spec-vector.ts
 * Output: docs/cloakvault-v3-test-vector.json
 *
 * The fixed inputs are TEST SECRETS ONLY — published deliberately so any
 * independent implementation can verify byte-for-byte interoperability.
 */
import { writeFileSync, mkdirSync } from 'node:fs';
import { bytesToHex, hexToBytes } from '../src/lib/crypto/bytes';
import { entropy32ToMnemonic, mnemonicToBip39Seed } from '../src/lib/crypto/wallet';
import { masterFingerprintFromSeed, formatFingerprint } from '../src/lib/crypto/fingerprint';
import { encodeVaultKey } from '../src/lib/crypto/vaultkey';
import { deriveCapsuleKeyV2, createCapsuleV2, CAPSULE2_KEY_INFO } from '../src/lib/crypto/capsule2';
import { rsEncode } from '../src/lib/rs/rs';
import { encodePayload, decodePayload, wrapToken, RS_PARITY_BYTES, SENTINEL } from '../src/lib/codec/footer';
import { renderFooter } from '../src/lib/pipeline';
import { openCapsuleV2 } from '../src/lib/crypto/capsule2';

// ── Fixed inputs (test secrets, published on purpose) ────────────────────────
const SEED_ENTROPY = hexToBytes('000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f');
const VAULT_KEY = hexToBytes('202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f');

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
if (!report.decoded || bytesToHex(report.capsule!) !== bytesToHex(capsule)) {
  throw new Error('self-check failed: decode path does not reproduce the capsule');
}
if (bytesToHex(openCapsuleV2(capsule, VAULT_KEY)) !== bytesToHex(SEED_ENTROPY)) {
  throw new Error('self-check failed: capsule does not open to the seed entropy');
}

const vector = {
  _warning: 'TEST SECRETS ONLY. Published deliberately for interoperability testing. Never reuse.',
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
    saltHex: '', // zero-length byte string
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
    systematic: 'codeword = data(49) || parity(34), parity highest-degree remainder coefficient first',
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

mkdirSync('docs', { recursive: true });
writeFileSync('docs/cloakvault-v3-test-vector.json', JSON.stringify(vector, null, 2) + '\n');
console.log('Wrote docs/cloakvault-v3-test-vector.json');
console.log('token:', token);
console.log('capsule:', bytesToHex(capsule));
console.log('derivedKey:', bytesToHex(derivedKey));
console.log('fingerprint:', fingerprint);
console.log('vaultKeyText:', vaultKeyText);
console.log('mnemonic:', mnemonic);
console.log('parityHex:', bytesToHex(codeword.slice(49)));
console.log('footerLine0:', footer.lines[0]);
