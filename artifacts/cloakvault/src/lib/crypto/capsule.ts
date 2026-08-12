/**
 * Recovery Capsule — exact 93-byte binary layout:
 *
 *   version     1 byte   (0x01)
 *   generation  4 bytes  BE (initial generation = 1)
 *   capsuleID   16 bytes
 *   nonce       24 bytes
 *   ciphertext  32 bytes
 *   tag         16 bytes
 *   ----------------------
 *   TOTAL       93 bytes
 *
 * AAD = first 21 bytes of capsule: version || generation || capsuleID.
 *
 * All failure conditions (wrong key, altered generation/ID/ciphertext/tag,
 * malformed length, invalid version) produce the same RECOVERY FAILED
 * outcome — parsing/decryption throws CapsuleError and no partial plaintext
 * is ever exposed.
 */
import type { RNG } from './rng';
import { deriveCapsuleKey } from './kdf';
import { aeadEncrypt, aeadDecrypt } from './aead';
import { concatBytes, u32be, readU32be, wipe } from './bytes';

export const CAPSULE_VERSION = 0x01;
export const CAPSULE_LENGTH = 93;
export const INITIAL_GENERATION = 1;

export class CapsuleError extends Error {
  constructor(reason: string) {
    super(reason);
    this.name = 'CapsuleError';
  }
}

export interface CapsuleFields {
  version: number;
  generation: number;
  capsuleId: Uint8Array;
  nonce: Uint8Array;
  ciphertext: Uint8Array;
  tag: Uint8Array;
}

export function serializeCapsule(f: CapsuleFields): Uint8Array {
  if (f.capsuleId.length !== 16) throw new CapsuleError('capsuleID must be 16 bytes');
  if (f.nonce.length !== 24) throw new CapsuleError('nonce must be 24 bytes');
  if (f.ciphertext.length !== 32) throw new CapsuleError('ciphertext must be 32 bytes');
  if (f.tag.length !== 16) throw new CapsuleError('tag must be 16 bytes');
  const out = concatBytes(
    new Uint8Array([f.version]),
    u32be(f.generation),
    f.capsuleId,
    f.nonce,
    f.ciphertext,
    f.tag,
  );
  if (out.length !== CAPSULE_LENGTH) throw new CapsuleError('capsule serialization error');
  return out;
}

export function parseCapsule(bytes: Uint8Array): CapsuleFields {
  if (bytes.length !== CAPSULE_LENGTH) {
    throw new CapsuleError(`malformed length: expected 93 bytes, got ${bytes.length}`);
  }
  const version = bytes[0];
  if (version !== CAPSULE_VERSION) {
    throw new CapsuleError('invalid capsule version');
  }
  return {
    version,
    generation: readU32be(bytes, 1),
    capsuleId: bytes.slice(5, 21),
    nonce: bytes.slice(21, 45),
    ciphertext: bytes.slice(45, 77),
    tag: bytes.slice(77, 93),
  };
}

/** Build the AAD (first 21 bytes): version || generation BE || capsuleID. */
export function capsuleAad(version: number, generation: number, capsuleId: Uint8Array): Uint8Array {
  return concatBytes(new Uint8Array([version]), u32be(generation), capsuleId);
}

/**
 * Create a capsule from 32-byte seed entropy and a Vault Key.
 * Capsule ID (16 bytes) and nonce (24 bytes) come from the injected RNG.
 */
export function createCapsule(
  seedEntropy: Uint8Array,
  vaultKey: Uint8Array,
  rng: RNG,
  generation: number = INITIAL_GENERATION,
): Uint8Array {
  if (seedEntropy.length !== 32) throw new CapsuleError('seed entropy must be 32 bytes');
  const capsuleId = rng.randomBytes(16);
  const nonce = rng.randomBytes(24);
  const capsuleKey = deriveCapsuleKey(vaultKey, capsuleId, generation);
  try {
    const aad = capsuleAad(CAPSULE_VERSION, generation, capsuleId);
    const { ciphertext, tag } = aeadEncrypt(capsuleKey, nonce, seedEntropy, aad);
    return serializeCapsule({
      version: CAPSULE_VERSION,
      generation,
      capsuleId,
      nonce,
      ciphertext,
      tag,
    });
  } finally {
    wipe(capsuleKey);
  }
}

/**
 * Open a capsule with the Vault Key. Returns the exact 32-byte seed entropy
 * or throws CapsuleError. Binary outcome; never partial plaintext.
 */
export function openCapsule(capsuleBytes: Uint8Array, vaultKey: Uint8Array): Uint8Array {
  const f = parseCapsule(capsuleBytes);
  const capsuleKey = deriveCapsuleKey(vaultKey, f.capsuleId, f.generation);
  try {
    const aad = capsuleAad(f.version, f.generation, f.capsuleId);
    let plaintext: Uint8Array;
    try {
      plaintext = aeadDecrypt(capsuleKey, f.nonce, f.ciphertext, f.tag, aad);
    } catch {
      throw new CapsuleError('authentication failed');
    }
    if (plaintext.length !== 32) {
      wipe(plaintext);
      throw new CapsuleError('unexpected plaintext length');
    }
    return plaintext;
  } finally {
    wipe(capsuleKey);
  }
}
