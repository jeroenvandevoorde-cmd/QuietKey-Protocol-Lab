/**
 * Cross-implementation interop check (acceptance criterion 5).
 *
 * TS → Python: TypeScript generates a fresh token; Python must decode it.
 * Python → TS: Python generates a fresh token; TypeScript must decode it.
 * This compares OUTPUTS only; no source is shared between implementations.
 *
 * Run: cd artifacts/cloakvault && npx tsx scripts/interop-check.ts
 * (expects interop/python/.venv to exist)
 */
import { execFileSync } from 'node:child_process';
import { writeFileSync, readFileSync, mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { bytesToHex, hexToBytes } from '../src/lib/crypto/bytes';
import { createCapsuleV2, openCapsuleV2 } from '../src/lib/crypto/capsule2';
import { encodePayload, decodePayload } from '../src/lib/codec/footer';

const PY = 'interop/python/.venv/bin/python';
const dir = mkdtempSync(join(tmpdir(), 'cv-interop-'));

// Fresh test values — NOT from the published vector.
const entropy = hexToBytes('f0e1d2c3b4a5968778695a4b3c2d1e0f00112233445566778899aabbccddeeff');
const vaultKey = hexToBytes('deadbeefcafef00d0123456789abcdeffedcba98765432100f1e2d3c4b5a6978');

let failures = 0;
const check = (name: string, ok: boolean, detail = '') => {
  console.log(`${ok ? 'PASS' : 'FAIL'}  ${name}${detail ? ` — ${detail}` : ''}`);
  if (!ok) failures++;
};

// ── TS → Python ───────────────────────────────────────────────────────────────
const tsToken = encodePayload(createCapsuleV2(entropy, vaultKey));
writeFileSync(join(dir, 'ts-token.txt'), tsToken);
const pyDecoded = execFileSync(PY, [
  '-c',
  `
import sys; sys.path.insert(0, 'interop/python')
import cloakvault_v3 as cv
token = open('${join(dir, 'ts-token.txt')}').read().strip()
entropy = cv.decode_pipeline(token, bytes.fromhex('${bytesToHex(vaultKey)}'))
print(entropy.hex())
`,
]).toString().trim();
check('TS-generated token decodes in Python to the exact entropy', pyDecoded === bytesToHex(entropy));

// ── Python → TS ───────────────────────────────────────────────────────────────
const pyToken = execFileSync(PY, [
  '-c',
  `
import sys; sys.path.insert(0, 'interop/python')
import cloakvault_v3 as cv
token = cv.encode_pipeline(bytes.fromhex('${bytesToHex(entropy)}'), bytes.fromhex('${bytesToHex(vaultKey)}'))
print(token)
`,
]).toString().trim();
check('Python and TS produce the IDENTICAL token (deterministic protocol)', pyToken === tsToken);
const report = decodePayload(pyToken);
const opened = report.capsule ? openCapsuleV2(report.capsule, vaultKey) : null;
check(
  'Python-generated token decodes in TypeScript to the exact entropy',
  opened !== null && bytesToHex(opened) === bytesToHex(entropy),
);

rmSync(dir, { recursive: true, force: true });
if (failures > 0) {
  console.error(`\n${failures} interop check(s) FAILED`);
  process.exit(1);
}
console.log('\nAll cross-implementation interop checks passed.');
