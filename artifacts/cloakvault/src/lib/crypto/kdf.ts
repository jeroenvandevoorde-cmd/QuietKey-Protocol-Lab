/**
 * Capsule key derivation (exact per spec):
 *
 *   capsuleKey = HKDF-SHA256(
 *     ikm    = K (Vault Key, 32 bytes),
 *     salt   = capsuleID (16 bytes),
 *     info   = UTF8("CLOAKVAULT-V1-CAPSULE-KEY") || generation (4 bytes BE),
 *     length = 32
 *   )
 */
import { hkdf } from '@noble/hashes/hkdf.js';
import { sha256 } from '@noble/hashes/sha2.js';
import { concatBytes, u32be } from './bytes';

export const CAPSULE_KEY_INFO = 'CLOAKVAULT-V1-CAPSULE-KEY';

export function deriveCapsuleKey(
  vaultKey: Uint8Array,
  capsuleId: Uint8Array,
  generation: number,
): Uint8Array {
  if (vaultKey.length !== 32) throw new Error('Vault Key must be 32 bytes.');
  if (capsuleId.length !== 16) throw new Error('Capsule ID must be 16 bytes.');
  const info = concatBytes(
    new TextEncoder().encode(CAPSULE_KEY_INFO),
    u32be(generation),
  );
  return hkdf(sha256, vaultKey, capsuleId, info, 32);
}
