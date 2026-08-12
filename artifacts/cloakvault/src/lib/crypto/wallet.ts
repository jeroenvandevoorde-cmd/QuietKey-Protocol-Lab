/**
 * BIP39 seed handling.
 *
 * The wallet seed is 32 bytes of entropy mapped to/from a 24-word English
 * BIP39 mnemonic using @scure/bip39. Invalid word counts, unknown words,
 * and invalid checksums are rejected. A user-supplied mnemonic is never
 * altered or "corrected".
 */
import {
  entropyToMnemonic,
  mnemonicToEntropy,
  mnemonicToSeedSync,
  validateMnemonic,
} from '@scure/bip39';
import { wordlist } from '@scure/bip39/wordlists/english.js';

/** Fixed test mnemonic: the BIP39 mnemonic of all-zero 256-bit entropy. */
export const FIXED_TEST_MNEMONIC = `${'abandon '.repeat(23)}art`.trim();

export interface MnemonicValidation {
  valid: boolean;
  error?: string;
}

/** Normalize whitespace ONLY (no word alteration). */
export function normalizeMnemonicWhitespace(mnemonic: string): string {
  return mnemonic.trim().toLowerCase().split(/\s+/).join(' ');
}

export function validateMnemonic24(mnemonic: string): MnemonicValidation {
  const normalized = normalizeMnemonicWhitespace(mnemonic);
  const words = normalized.length === 0 ? [] : normalized.split(' ');
  if (words.length !== 24) {
    return { valid: false, error: `Expected 24 words, got ${words.length}.` };
  }
  const wordSet = new Set(wordlist);
  for (const w of words) {
    if (!wordSet.has(w)) {
      return { valid: false, error: `"${w}" is not a BIP39 English word.` };
    }
  }
  if (!validateMnemonic(normalized, wordlist)) {
    return { valid: false, error: 'Invalid BIP39 checksum.' };
  }
  return { valid: true };
}

/** 24-word mnemonic -> 32-byte entropy. Throws on any invalid input. */
export function mnemonicToEntropy32(mnemonic: string): Uint8Array {
  const normalized = normalizeMnemonicWhitespace(mnemonic);
  const check = validateMnemonic24(normalized);
  if (!check.valid) throw new Error(check.error);
  const entropy = mnemonicToEntropy(normalized, wordlist);
  if (entropy.length !== 32) throw new Error('Entropy is not 32 bytes.');
  return entropy;
}

/** 32-byte entropy -> 24-word mnemonic. */
export function entropy32ToMnemonic(entropy: Uint8Array): string {
  if (entropy.length !== 32) throw new Error('Entropy must be exactly 32 bytes.');
  return entropyToMnemonic(entropy, wordlist);
}

/** BIP39 mnemonic (+ optional passphrase) -> 64-byte BIP39 seed. */
export function mnemonicToBip39Seed(mnemonic: string, passphrase = ''): Uint8Array {
  return mnemonicToSeedSync(mnemonic, passphrase);
}
