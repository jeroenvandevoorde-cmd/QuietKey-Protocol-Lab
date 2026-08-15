/**
 * CloakVault v3 Footer Codec.
 *
 * Encode:  49-byte capsule ─ RS(n, 49) over GF(2^8), parity = RS_PARITY_BYTES ─►
 *          n-byte codeword ─ 5-bit groups ─► Bech32 chars ─►
 *          token = SENTINEL ("cv0") + data chars + 6-char Bech32 checksum.
 *
 * Shipped default (robust end, per damage test): RS_PARITY_BYTES = 34 →
 * n = 83, k = 49, codeword 664 bits → 133 data chars (1 zero pad bit),
 * token length 3 + 133 + 6 = 142 characters.
 *   - theoretical max erasures: 34 bytes;  max errors: 17 bytes (2e + s ≤ 34).
 *
 * Self-delimiting and genre-independent: the decoder locates the token by
 * its own structure — the sentinel prefix + expected length + checksum —
 * never by surrounding URL text, domain, or parameter name. Fallback: if
 * the sentinel itself is damaged, any maximal run of alphabet/'?' characters
 * of the expected token length is tried.
 *
 * Erasure interface: unreadable characters are marked '?' in the input.
 * Each erased character maps to erasures on every codeword byte it overlaps
 * (a 5-bit char spans at most 2 bytes). The decoder NEVER guesses damaged
 * characters.
 */
import { rsEncode, rsDecode, RSUncorrectable } from '@/lib/rs/rs';
import { CAPSULE2_LENGTH } from '@/lib/crypto/capsule2';
import {
  BECH32_CHARSET,
  createChecksum,
  verifyChecksum,
  charToValue,
  valueToChar,
} from './bech32';

/** Configurable parity — single constant, tuned empirically via the damage harness. */
export const RS_PARITY_BYTES = 34;
export const SENTINEL = 'cv0';
export const ERASURE_MARK = '?';
/** Wrap width when rendering into the printed footer (like a long URL wrapping). */
export const FOOTER_WRAP_WIDTH = 48;

export function codecParams(parity: number = RS_PARITY_BYTES) {
  const k = CAPSULE2_LENGTH;
  const n = k + parity;
  const dataChars = Math.ceil((n * 8) / 5);
  return {
    n,
    k,
    parity,
    dataChars,
    tokenLength: SENTINEL.length + dataChars + 6,
    maxErasures: parity,
    maxErrors: Math.floor(parity / 2),
  };
}

/** 49-byte capsule → complete token string (sentinel + data + checksum). */
export function encodePayload(capsule: Uint8Array, parity: number = RS_PARITY_BYTES): string {
  if (capsule.length !== CAPSULE2_LENGTH) throw new Error('payload must be a 49-byte capsule');
  const codeword = rsEncode(capsule, parity);
  const values: number[] = [];
  let acc = 0;
  let bits = 0;
  for (const byte of codeword) {
    acc = (acc << 8) | byte;
    bits += 8;
    while (bits >= 5) {
      values.push((acc >>> (bits - 5)) & 31);
      bits -= 5;
    }
  }
  if (bits > 0) values.push((acc << (5 - bits)) & 31); // zero-pad final group
  const checksum = createChecksum(values);
  return SENTINEL + values.map(valueToChar).join('') + checksum.map(valueToChar).join('');
}

/** Wrap a token across lines like a printed long URL (layout defense). */
export function wrapToken(token: string, width: number = FOOTER_WRAP_WIDTH): string[] {
  const lines: string[] = [];
  for (let i = 0; i < token.length; i += width) lines.push(token.slice(i, i + width));
  return lines;
}

export interface ExtractResult {
  token: string | null;
  method: 'sentinel' | 'run' | null;
}

/**
 * Locate the payload token inside arbitrary pasted text (whole footer lines,
 * URLs and all). Structure-only: sentinel match first, then a
 * expected-length run fallback. Whitespace/newlines inside the token
 * (from line wrapping) are ignored.
 */
export function extractToken(text: string, parity: number = RS_PARITY_BYTES): ExtractResult {
  const { tokenLength } = codecParams(parity);
  const isTokenChar = (c: string) => charToValue(c) !== undefined || c === ERASURE_MARK;
  // Collapse whitespace so wrapped lines rejoin, tracking only token-ish runs.
  const compact = [...text.toLowerCase()].filter((c) => !/\s/.test(c)).join('');
  const runs: { start: number; str: string }[] = [];
  let cur = '';
  let curStart = 0;
  for (let i = 0; i <= compact.length; i++) {
    const c = compact[i];
    if (c !== undefined && isTokenChar(c)) {
      if (cur === '') curStart = i;
      cur += c;
    } else if (cur) {
      runs.push({ start: curStart, str: cur });
      cur = '';
    }
  }
  // 1) Sentinel match inside any run.
  for (const r of runs) {
    const at = r.str.indexOf(SENTINEL);
    if (at >= 0 && r.str.length - at >= tokenLength) {
      return { token: r.str.slice(at, at + tokenLength), method: 'sentinel' };
    }
  }
  // 2) Fallback: a run of exactly/at least the token length (sentinel damaged).
  for (const r of runs) {
    if (r.str.length >= tokenLength) {
      return { token: r.str.slice(r.str.length - tokenLength), method: 'run' };
    }
  }
  return { token: null, method: null };
}

export interface DecodeReport {
  extracted: boolean;
  extractMethod: 'sentinel' | 'run' | null;
  checksumValid: boolean | null; // null = unverifiable (erasure marks present)
  decoded: boolean;
  erasuresUsed: number; // codeword BYTES declared as erasures
  errorsCorrected: number; // codeword BYTES RS both located and corrected
  parityBudgetUsed: number; // 2·errors + erasures
  parityBudget: number; // total parity bytes
  capsule: Uint8Array | null;
  failure: string | null;
}

/** Full instrumented decode: pasted text → 49-byte capsule or typed failure. */
export function decodePayload(text: string, parity: number = RS_PARITY_BYTES): DecodeReport {
  const params = codecParams(parity);
  const base: DecodeReport = {
    extracted: false,
    extractMethod: null,
    checksumValid: null,
    decoded: false,
    erasuresUsed: 0,
    errorsCorrected: 0,
    parityBudgetUsed: 0,
    parityBudget: parity,
    capsule: null,
    failure: null,
  };
  const { token, method } = extractToken(text, parity);
  if (!token) return { ...base, failure: 'no payload token found in the pasted text' };
  base.extracted = true;
  base.extractMethod = method;

  // Sentinel positions are structural only; data+checksum follow it.
  const body = token.slice(SENTINEL.length);
  const values: (number | null)[] = [...body].map((c) =>
    c === ERASURE_MARK ? null : (charToValue(c) ?? null),
  );
  const hasErasures = values.some((v) => v === null);
  if (!hasErasures) {
    base.checksumValid = verifyChecksum(values as number[]);
  }

  // 5-bit values (checksum chars excluded) → n bytes; erased chars → byte erasures.
  const dataValues = values.slice(0, params.dataChars);
  const bytes = new Uint8Array(params.n);
  const erased = new Set<number>();
  let acc = 0;
  let bits = 0;
  let byteIdx = 0;
  dataValues.forEach((v, charIdx) => {
    const bitStart = charIdx * 5;
    if (v === null) {
      // Mark every byte this character overlaps as an erasure.
      erased.add(Math.floor(bitStart / 8));
      const endByte = Math.floor((bitStart + 4) / 8);
      if (endByte < params.n) erased.add(endByte);
    }
    acc = (acc << 5) | (v ?? 0);
    bits += 5;
    while (bits >= 8 && byteIdx < params.n) {
      bytes[byteIdx++] = (acc >>> (bits - 8)) & 0xff;
      bits -= 8;
    }
  });

  base.erasuresUsed = erased.size;
  try {
    const data = rsDecode(bytes, parity, [...erased].sort((a, b) => a - b));
    // Count corrections by re-encoding the recovered data and diffing.
    const reencoded = rsEncode(data, parity);
    let errors = 0;
    for (let i = 0; i < params.n; i++) {
      if (reencoded[i] !== bytes[i] && !erased.has(i)) errors++;
    }
    base.errorsCorrected = errors;
    base.parityBudgetUsed = 2 * errors + erased.size;
    if (data.length !== CAPSULE2_LENGTH) {
      return { ...base, failure: 'decoded payload has wrong length' };
    }
    base.decoded = true;
    base.capsule = data;
    return base;
  } catch (e) {
    const msg = e instanceof RSUncorrectable ? 'damage exceeds the correction budget' : 'decode failed';
    return { ...base, failure: msg };
  }
}

/** Sanity: charset is exactly the Bech32 one. */
if (BECH32_CHARSET.length !== 32) throw new Error('invalid charset');
