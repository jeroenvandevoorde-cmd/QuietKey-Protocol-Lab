/**
 * Injectable RNG abstraction.
 *
 * All protocol randomness (Vault Key, Capsule ID, AEAD nonce, share
 * randomness) MUST flow through this interface.
 *
 * - SystemRNG: Browser-laboratory RNG (`crypto.getRandomValues`).
 *   The production QuietKey terminal entropy architecture — multiple
 *   designated independent entropy sources combined through a specified
 *   conditioner and subject to health testing under QK2-04 — is NOT modeled
 *   here and must never be derived from this file. `SystemRNG` exists only
 *   to support the Browser Protocol Laboratory.
 * - DeterministicTestRNG is a seeded deterministic generator used ONLY by
 *   tests and the deterministic test-vector export. It must never be
 *   reachable from a normal laboratory Create flow.
 */
import { sha256 } from '@noble/hashes/sha2.js';

export interface RNG {
  /** Fill and return a new Uint8Array of `length` random bytes. */
  randomBytes(length: number): Uint8Array;
}

export class SystemRNG implements RNG {
  randomBytes(length: number): Uint8Array {
    const out = new Uint8Array(length);
    crypto.getRandomValues(out);
    return out;
  }
}

/**
 * Deterministic seeded byte stream for tests and vector export.
 *
 * Construction (fixed; part of the test-vector definition, NOT a protocol
 * cryptographic primitive):
 *
 *   block_i = SHA-256( seed(32) || uint64_be(i) ),  i = 0,1,2,...
 *   stream  = block_0 || block_1 || ...
 *
 * randomBytes(n) returns the next n bytes of the stream.
 */
export class DeterministicTestRNG implements RNG {
  private readonly seed: Uint8Array;
  private counter = 0n;
  private buffer = new Uint8Array(0);
  private offset = 0;

  constructor(seed: Uint8Array) {
    if (seed.length !== 32) {
      throw new Error('DeterministicTestRNG seed must be 32 bytes');
    }
    this.seed = seed.slice();
  }

  static fromSeedNumber(n: number): DeterministicTestRNG {
    const seed = new Uint8Array(32);
    const view = new DataView(seed.buffer);
    view.setUint32(28, n >>> 0, false);
    return new DeterministicTestRNG(seed);
  }

  private refill(): void {
    const input = new Uint8Array(40);
    input.set(this.seed, 0);
    const view = new DataView(input.buffer);
    view.setBigUint64(32, this.counter, false);
    this.counter += 1n;
    this.buffer = sha256(input);
    this.offset = 0;
  }

  randomBytes(length: number): Uint8Array {
    const out = new Uint8Array(length);
    let filled = 0;
    while (filled < length) {
      if (this.offset >= this.buffer.length) this.refill();
      const take = Math.min(length - filled, this.buffer.length - this.offset);
      out.set(this.buffer.subarray(this.offset, this.offset + take), filled);
      this.offset += take;
      filled += take;
    }
    return out;
  }
}
