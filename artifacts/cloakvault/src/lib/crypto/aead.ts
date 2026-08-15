/**
 * AEAD: XChaCha20-Poly1305 from @noble/ciphers.
 *
 * noble's xchacha20poly1305 returns ciphertext || tag; this module exposes
 * them separately to match the capsule layout (ciphertext 32 + tag 16).
 */
import { xchacha20poly1305 } from '@noble/ciphers/chacha.js';
import { concatBytes } from './bytes';

export const TAG_LENGTH = 16;

export interface AeadResult {
  ciphertext: Uint8Array;
  tag: Uint8Array;
}

export function aeadEncrypt(
  key: Uint8Array,
  nonce: Uint8Array,
  plaintext: Uint8Array,
  aad: Uint8Array,
): AeadResult {
  if (key.length !== 32) throw new Error('AEAD key must be 32 bytes.');
  if (nonce.length !== 24) throw new Error('AEAD nonce must be 24 bytes.');
  const sealed = xchacha20poly1305(key, nonce, aad).encrypt(plaintext);
  return {
    ciphertext: sealed.slice(0, sealed.length - TAG_LENGTH),
    tag: sealed.slice(sealed.length - TAG_LENGTH),
  };
}

/** Returns plaintext, or throws on authentication failure. */
export function aeadDecrypt(
  key: Uint8Array,
  nonce: Uint8Array,
  ciphertext: Uint8Array,
  tag: Uint8Array,
  aad: Uint8Array,
): Uint8Array {
  if (key.length !== 32) throw new Error('AEAD key must be 32 bytes.');
  if (nonce.length !== 24) throw new Error('AEAD nonce must be 24 bytes.');
  if (tag.length !== TAG_LENGTH) throw new Error('AEAD tag must be 16 bytes.');
  return xchacha20poly1305(key, nonce, aad).decrypt(concatBytes(ciphertext, tag));
}
