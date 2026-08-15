/**
 * Vault Key: 32 random bytes from the injected RNG.
 *
 * Canonical test/display representation:
 *   payload  = 0x01 || K (33 bytes)
 *   checksum = first 4 bytes of SHA-256(payload)
 *   encoded  = CrockfordBase32(payload || checksum)   (37 bytes -> 60 chars)
 *   display  = "CVK1." + encoded grouped into blocks of four
 *
 * The Vault Key is never rendered as BIP39 words or any word phrase.
 */
import { sha256 } from '@noble/hashes/sha2.js';
import type { RNG } from './rng';
import { crockfordEncode, crockfordDecode, groupBy4 } from './base32';
import { concatBytes, equalBytes } from './bytes';

export const VAULT_KEY_PREFIX = 'CVK1.';
const VERSION_BYTE = 0x01;
const PAYLOAD_LEN = 33; // version + 32 key bytes
const TOTAL_LEN = PAYLOAD_LEN + 4;

export function generateVaultKey(rng: RNG): Uint8Array {
  return rng.randomBytes(32);
}

export function encodeVaultKey(key: Uint8Array): string {
  if (key.length !== 32) throw new Error('Vault Key must be 32 bytes.');
  const payload = concatBytes(new Uint8Array([VERSION_BYTE]), key);
  const checksum = sha256(payload).slice(0, 4);
  const encoded = crockfordEncode(concatBytes(payload, checksum));
  return VAULT_KEY_PREFIX + groupBy4(encoded);
}

/** Strict decode; throws with a specific reason on any mismatch. */
export function decodeVaultKey(text: string): Uint8Array {
  const trimmed = text.trim();
  if (!trimmed.toUpperCase().startsWith(VAULT_KEY_PREFIX)) {
    throw new Error('Missing CVK1. prefix.');
  }
  const body = trimmed.slice(VAULT_KEY_PREFIX.length);
  const raw = crockfordDecode(body, TOTAL_LEN);
  const payload = raw.slice(0, PAYLOAD_LEN);
  const checksum = raw.slice(PAYLOAD_LEN);
  if (payload[0] !== VERSION_BYTE) {
    throw new Error('Unsupported Vault Key version.');
  }
  const expected = sha256(payload).slice(0, 4);
  if (!equalBytes(checksum, expected)) {
    throw new Error('Vault Key checksum mismatch.');
  }
  return payload.slice(1);
}
