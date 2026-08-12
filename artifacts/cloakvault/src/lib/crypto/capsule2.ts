/**
 * Recovery Capsule v2 — exact 49-byte binary layout (CloakVault v3):
 *
 *   version     1 byte   (0x02)
 *   ciphertext  32 bytes (AES-256-GCM-SIV over the 32-byte seed entropy)
 *   tag         16 bytes (GCM-SIV tag, full length — never truncated)
 *   ----------------------
 *   TOTAL       49 bytes
 *
 * FROZEN PROTOCOL CONSTANTS (owner ruling; an independent recovery
 * implementation must reproduce these verbatim):
 *
 *   AEAD:   AEAD_AES_256_GCM_SIV (RFC 8452), via @noble/ciphers `gcmsiv`.
 *   Nonce:  fixed all-zero 12 bytes. NOT stored.
 *   Key:    capsuleKey = HKDF-SHA256(
 *             ikm  = Vault Key (32 bytes, full-entropy),
 *             salt = EMPTY (zero-length byte string — not 32 zero bytes),
 *             info = UTF-8 bytes of the exact ASCII string
 *                    "CLOAKVAULT-V3-CAPSULE-KEY" (25 bytes, no terminator),
 *             length = 32)
 *   AAD:    the 1-byte version prefix (0x02), binding the header.
 *
 * DETERMINISTIC-EQUALITY PROPERTY (intended, not a bug): encryption is fully
 * deterministic — the identical seed under the identical Vault Key yields a
 * byte-identical capsule. This is REQUIRED for equivalent-card redundancy
 * (two independently printed cards for the same seed+key must carry the same
 * payload). Under RFC 8452's misuse-resistance this leaks only equality.
 * Do NOT "fix" this by adding randomness; that silently breaks equivalence.
 *
 * All failure conditions (wrong key, altered version/ciphertext/tag,
 * malformed length) produce the same typed Capsule2Error — binary outcome,
 * never partial plaintext.
 */
import { gcmsiv } from '@noble/ciphers/aes.js';
import { hkdf } from '@noble/hashes/hkdf.js';
import { sha256 } from '@noble/hashes/sha2.js';
import { wipe } from './bytes';

export const CAPSULE2_VERSION = 0x02;
export const CAPSULE2_LENGTH = 49;
export const CAPSULE2_KEY_INFO = 'CLOAKVAULT-V3-CAPSULE-KEY';
export const CAPSULE2_NONCE = new Uint8Array(12); // fixed all-zero, not stored

export class Capsule2Error extends Error {
  constructor(reason: string) {
    super(reason);
    this.name = 'Capsule2Error';
  }
}

/** HKDF-SHA256(ikm=VaultKey, salt=empty, info="CLOAKVAULT-V3-CAPSULE-KEY", 32). */
export function deriveCapsuleKeyV2(vaultKey: Uint8Array): Uint8Array {
  if (vaultKey.length !== 32) throw new Capsule2Error('Vault Key must be 32 bytes');
  return hkdf(sha256, vaultKey, new Uint8Array(0), new TextEncoder().encode(CAPSULE2_KEY_INFO), 32);
}

/** 32-byte seed entropy + Vault Key → 49-byte capsule. Deterministic; no RNG. */
export function createCapsuleV2(seedEntropy: Uint8Array, vaultKey: Uint8Array): Uint8Array {
  if (seedEntropy.length !== 32) throw new Capsule2Error('seed entropy must be 32 bytes');
  const key = deriveCapsuleKeyV2(vaultKey);
  try {
    const aad = new Uint8Array([CAPSULE2_VERSION]);
    const sealed = gcmsiv(key, CAPSULE2_NONCE, aad).encrypt(seedEntropy); // ct(32) || tag(16)
    if (sealed.length !== 48) throw new Capsule2Error('AEAD output length error');
    const out = new Uint8Array(CAPSULE2_LENGTH);
    out[0] = CAPSULE2_VERSION;
    out.set(sealed, 1);
    return out;
  } finally {
    wipe(key);
  }
}

/** 49-byte capsule + Vault Key → exact 32-byte seed entropy, or Capsule2Error. */
export function openCapsuleV2(capsule: Uint8Array, vaultKey: Uint8Array): Uint8Array {
  if (capsule.length !== CAPSULE2_LENGTH) {
    throw new Capsule2Error(`malformed length: expected 49 bytes, got ${capsule.length}`);
  }
  if (capsule[0] !== CAPSULE2_VERSION) throw new Capsule2Error('invalid capsule version');
  const key = deriveCapsuleKeyV2(vaultKey);
  try {
    const aad = new Uint8Array([CAPSULE2_VERSION]);
    return gcmsiv(key, CAPSULE2_NONCE, aad).decrypt(capsule.slice(1));
  } catch (e) {
    if (e instanceof Capsule2Error) throw e;
    throw new Capsule2Error('authentication failed');
  } finally {
    wipe(key);
  }
}
