/**
 * READ-ONLY verifier for the frozen CloakVault v3 conformance vector.
 *
 * Run: cd artifacts/cloakvault && npx tsx scripts/verify-spec-vector.ts
 *      [--vector <path>]   read-only alternate vector (for deliberately
 *                          corrupted temporary copies during acceptance
 *                          testing). Default: the canonical checked-in
 *                          docs/cloakvault-v3-test-vector.json.
 *
 * This script has NO write path. It cannot create, replace, regenerate, or
 * update the canonical vector. The frozen vector is the expected input; the
 * implementation never gets to redefine the expected answer. A future
 * protocol version requires separate, explicitly approved tooling and a new
 * vector filename — it does not overwrite v3.
 *
 * Behavior: load the frozen vector, recompute every byte-determining /
 * interoperability field in memory from the vector's fixed test inputs using
 * the reference implementation, and compare field-by-field. PASS on full
 * match; on any mismatch print a field-level expected-vs-computed diff and
 * exit nonzero.
 */
import { readFileSync } from 'node:fs';
import { bytesToHex, hexToBytes } from '../src/lib/crypto/bytes';
import { entropy32ToMnemonic, mnemonicToBip39Seed } from '../src/lib/crypto/wallet';
import { masterFingerprintFromSeed, formatFingerprint } from '../src/lib/crypto/fingerprint';
import { encodeVaultKey } from '../src/lib/crypto/vaultkey';
import { deriveCapsuleKeyV2, createCapsuleV2, CAPSULE2_KEY_INFO } from '../src/lib/crypto/capsule2';
import { rsEncode } from '../src/lib/rs/rs';
import { encodePayload, RS_PARITY_BYTES, SENTINEL } from '../src/lib/codec/footer';
import { renderFooter } from '../src/lib/pipeline';

const CANONICAL = 'docs/cloakvault-v3-test-vector.json';

const argIdx = process.argv.indexOf('--vector');
const vectorPath = argIdx >= 0 ? process.argv[argIdx + 1] : CANONICAL;
if (argIdx >= 0 && !vectorPath) {
  console.error('--vector requires a path argument');
  process.exit(2);
}

const vector = JSON.parse(readFileSync(vectorPath, 'utf8'));

// ── Recompute candidate values in memory from the vector's fixed inputs ──────
const seedEntropy = hexToBytes(vector.inputs.seedEntropyHex);
const vaultKey = hexToBytes(vector.inputs.vaultKeyHex);

const mnemonic = entropy32ToMnemonic(seedEntropy);
const bip39Seed = mnemonicToBip39Seed(mnemonic);
const fingerprint = formatFingerprint(masterFingerprintFromSeed(bip39Seed));
const vaultKeyText = encodeVaultKey(vaultKey);
const derivedKey = deriveCapsuleKeyV2(vaultKey);
const capsule = createCapsuleV2(seedEntropy, vaultKey);
const codeword = rsEncode(capsule, RS_PARITY_BYTES);
const token = encodePayload(capsule);
// The frozen vector's footer lines embed the printed date rendered when the
// vector was frozen; recover it from the vector's own rendering so the
// comparison covers the deterministic parts byte-for-byte.
const frozenDateMatch = (vector.rendering.footerLines as string[])
  .join('\n')
  .match(/Printed (\d{2}\/\d{2}\/\d{4})/);
const printedDate = frozenDateMatch ? frozenDateMatch[1] : '12/08/2026';
const footer = renderFooter(token, printedDate);

// ── Field-by-field comparison ─────────────────────────────────────────────────
let failures = 0;
function check(field: string, expected: unknown, computed: unknown) {
  const e = JSON.stringify(expected);
  const c = JSON.stringify(computed);
  if (e === c) {
    console.log(`  ok   ${field}`);
  } else {
    failures++;
    console.log(`  FAIL ${field}`);
    console.log(`       expected (frozen vector): ${e}`);
    console.log(`       computed (implementation): ${c}`);
  }
}

console.log(`Verifying ${vectorPath} against the reference implementation…`);

check('inputs.mnemonic', vector.inputs.mnemonic, mnemonic);
check('inputs.vaultKeyText', vector.inputs.vaultKeyText, vaultKeyText);
check('hkdf.infoAscii', vector.hkdf.infoAscii, CAPSULE2_KEY_INFO);
check('hkdf.infoHex', vector.hkdf.infoHex, bytesToHex(new TextEncoder().encode(CAPSULE2_KEY_INFO)));
check('hkdf.saltHex', vector.hkdf.saltHex, '');
check('hkdf.outputLength', vector.hkdf.outputLength, 32);
check('hkdf.derivedCapsuleKeyHex', vector.hkdf.derivedCapsuleKeyHex, bytesToHex(derivedKey));
check('capsule.lengthBytes', vector.capsule.lengthBytes, capsule.length);
check('capsule.versionByte', vector.capsule.versionByte, '0x02');
check('capsule.aadHex', vector.capsule.aadHex, '02');
check('capsule.nonceHex', vector.capsule.nonceHex, '000000000000000000000000');
check('capsule.capsuleHex', vector.capsule.capsuleHex, bytesToHex(capsule));
check('capsule.ciphertextHex', vector.capsule.ciphertextHex, bytesToHex(capsule.slice(1, 33)));
check('capsule.tagHex', vector.capsule.tagHex, bytesToHex(capsule.slice(33)));
check('reedSolomon.n', vector.reedSolomon.n, 83);
check('reedSolomon.k', vector.reedSolomon.k, 49);
check('reedSolomon.parity', vector.reedSolomon.parity, RS_PARITY_BYTES);
check('reedSolomon.primitivePolynomial', vector.reedSolomon.primitivePolynomial, '0x11d');
check('reedSolomon.codewordHex', vector.reedSolomon.codewordHex, bytesToHex(codeword));
check('reedSolomon.parityHex', vector.reedSolomon.parityHex, bytesToHex(codeword.slice(49)));
check('bech32.charset', vector.bech32.charset, 'qpzry9x8gf2tvdw0s3jn54khce6mua7l');
check('bech32.hrp', vector.bech32.hrp, 'cv');
check('bech32.sentinel', vector.bech32.sentinel, SENTINEL);
check('bech32.dataChars', vector.bech32.dataChars, 133);
check('bech32.checksumChars', vector.bech32.checksumChars, 6);
check('bech32.tokenLength', vector.bech32.tokenLength, token.length);
check('bech32.token', vector.bech32.token, token);
check('rendering.wrapWidth', vector.rendering.wrapWidth, 48);
check('rendering.footerLines', vector.rendering.footerLines, footer.lines);
check('expectedRecovery.fingerprint', vector.expectedRecovery.fingerprint, fingerprint);
check('expectedRecovery.mnemonic', vector.expectedRecovery.mnemonic, mnemonic);

if (failures > 0) {
  console.log(`\nFAIL — ${failures} field(s) mismatched. The frozen vector is the expected value; fix the implementation, never the vector.`);
  process.exit(1);
}
console.log('\nPASS — implementation reproduces every frozen vector field byte-for-byte.');
