/**
 * LEGACY v1 (SUPERSEDED).
 *
 * This file implements the retired v1 Independent Recovery construction: a
 * 32-byte Vault-Key-only XOR split.
 *
 * Under the current QK2-04 architecture, Independent Recovery protects the
 * 64-byte `VaultKey ‖ keyB` payload.
 *
 * The current-format serialization and binding rules are a later Gate-B
 * deliverable and MUST NOT be improvised here.
 *
 * This file is retained as historical Browser Protocol Laboratory code only.
 * It must not be extended into the current architecture.
 *
 * Retired v1 construction (historical):
 *
 *   R = 32 random bytes
 *   Share A = R
 *   Share B = K XOR R
 *
 * Recovery: Share A XOR Share B = K.
 *
 * Share A text format:
 *   payload  = 0x01 || 0x0A || generation(4 BE) || shareBytes(32)  → 38 bytes
 *   checksum = first 4 bytes of SHA-256(payload)
 *   encoded  = CrockfordBase32(payload || checksum)                → 42 bytes → 68 chars
 *   display  = "CVSA1." + encoded grouped by 4
 *
 * Share B text format:
 *   payload  = 0x01 || 0x0B || generation(4 BE) || shareBytes(32)  → 38 bytes
 *   prefix   = "CVSB1."
 */
import { sha256 } from '@noble/hashes/sha2.js';
import type { RNG } from './rng';
import { concatBytes, equalBytes, u32be, readU32be, wipe } from './bytes';
import { crockfordEncode, crockfordDecode, groupBy4 } from './base32';
import { encodeVaultKey, VAULT_KEY_PREFIX } from './vaultkey';

export const SHARE_A_PREFIX = 'CVSA1.';
export const SHARE_B_PREFIX = 'CVSB1.';

const VERSION_BYTE = 0x01;
const INDEX_A = 0x0a;
const INDEX_B = 0x0b;
const PAYLOAD_LEN = 38; // version + index + generation(4) + shareBytes(32)
const TOTAL_LEN = PAYLOAD_LEN + 4; // + checksum

export interface Shares {
  shareA: string;
  shareB: string;
}

function encodeShare(
  index: number,
  generation: number,
  shareBytes: Uint8Array,
): string {
  if (shareBytes.length !== 32) throw new Error('share data must be 32 bytes');
  const payload = concatBytes(
    new Uint8Array([VERSION_BYTE, index]),
    u32be(generation),
    shareBytes,
  );
  const checksum = sha256(payload).slice(0, 4);
  return crockfordEncode(concatBytes(payload, checksum));
}

function decodeShare(
  text: string,
  expectedPrefix: string,
  expectedIndex: number,
): { generation: number; shareBytes: Uint8Array } {
  const trimmed = text.trim();
  if (!trimmed.toUpperCase().startsWith(expectedPrefix.toUpperCase())) {
    throw new Error(`Missing ${expectedPrefix} prefix.`);
  }
  const body = trimmed.slice(expectedPrefix.length);
  const raw = crockfordDecode(body, TOTAL_LEN);
  const payload = raw.slice(0, PAYLOAD_LEN);
  const checksum = raw.slice(PAYLOAD_LEN);
  const expected = sha256(payload).slice(0, 4);
  if (!equalBytes(checksum, expected)) {
    throw new Error(`Invalid ${expectedPrefix} checksum.`);
  }
  if (payload[0] !== VERSION_BYTE) {
    throw new Error(`Unsupported share version: ${payload[0]}.`);
  }
  if (payload[1] !== expectedIndex) {
    throw new Error(
      `Expected share index ${expectedIndex}, got ${payload[1]}.`,
    );
  }
  const generation = readU32be(payload, 2);
  return { generation, shareBytes: payload.slice(6) };
}

/**
 * Create Share A and Share B from a Vault Key.
 * R = 32 random bytes; shareA = R; shareB = K XOR R.
 */
export function createShares(
  vaultKey: Uint8Array,
  rng: RNG,
  generation = 1,
): Shares {
  if (vaultKey.length !== 32) throw new Error('Vault Key must be 32 bytes.');
  const r = rng.randomBytes(32);
  const shareABytes = r.slice();
  const shareBBytes = new Uint8Array(32);
  for (let i = 0; i < 32; i++) shareBBytes[i] = vaultKey[i] ^ r[i];

  const shareA =
    SHARE_A_PREFIX +
    groupBy4(encodeShare(INDEX_A, generation, shareABytes));
  const shareB =
    SHARE_B_PREFIX +
    groupBy4(encodeShare(INDEX_B, generation, shareBBytes));

  wipe(r, shareABytes, shareBBytes);
  return { shareA, shareB };
}

export class ShareError extends Error {
  constructor(msg: string) {
    super(msg);
    this.name = 'ShareError';
  }
}

/**
 * Rejoin Share A + Share B -> Vault Key string (CVK1.).
 * Throws ShareError with the exact mismatched field.
 */
export function rejoinShares(shareAText: string, shareBText: string): string {
  let a: ReturnType<typeof decodeShare>;
  let b: ReturnType<typeof decodeShare>;

  try {
    a = decodeShare(shareAText, SHARE_A_PREFIX, INDEX_A);
  } catch (e) {
    // Check if user swapped the inputs.
    if (shareAText.trim().toUpperCase().startsWith(SHARE_B_PREFIX.toUpperCase())) {
      throw new ShareError('Both inputs are Share B.');
    }
    throw new ShareError(String((e as Error).message));
  }

  try {
    b = decodeShare(shareBText, SHARE_B_PREFIX, INDEX_B);
  } catch (e) {
    if (shareBText.trim().toUpperCase().startsWith(SHARE_A_PREFIX.toUpperCase())) {
      throw new ShareError('Both inputs are Share A.');
    }
    throw new ShareError(String((e as Error).message));
  }

  if (a.generation !== b.generation) {
    throw new ShareError(
      `Generation mismatch: Share A generation ${a.generation}, Share B generation ${b.generation}.`,
    );
  }

  const vaultKey = new Uint8Array(32);
  for (let i = 0; i < 32; i++) vaultKey[i] = a.shareBytes[i] ^ b.shareBytes[i];
  wipe(a.shareBytes, b.shareBytes);

  const cvk = encodeVaultKey(vaultKey);
  wipe(vaultKey);
  return cvk;
}
