/**
 * Crockford Base32 (RFC-less; per https://www.crockford.com/base32.html).
 *
 * Encoding: bytes are treated as a big-endian bit string, consumed 5 bits at
 * a time MSB-first; the final group is zero-padded on the right. No padding
 * characters. Alphabet excludes I, L, O, U.
 *
 * Decoding: case-insensitive; I and L decode as 1, O decodes as 0. Hyphens
 * and whitespace are ignored. Any other character is rejected. Trailing pad
 * bits must be zero and the decoded length must match the expected length.
 */
const ALPHABET = '0123456789ABCDEFGHJKMNPQRSTVWXYZ';

const DECODE_MAP: Record<string, number> = (() => {
  const m: Record<string, number> = {};
  for (let i = 0; i < ALPHABET.length; i++) {
    m[ALPHABET[i]] = i;
    m[ALPHABET[i].toLowerCase()] = i;
  }
  m['O'] = 0; m['o'] = 0;
  m['I'] = 1; m['i'] = 1;
  m['L'] = 1; m['l'] = 1;
  return m;
})();

export function crockfordEncode(bytes: Uint8Array): string {
  let out = '';
  let acc = 0;
  let bits = 0;
  for (const b of bytes) {
    acc = (acc << 8) | b;
    bits += 8;
    while (bits >= 5) {
      out += ALPHABET[(acc >>> (bits - 5)) & 31];
      bits -= 5;
    }
  }
  if (bits > 0) {
    out += ALPHABET[(acc << (5 - bits)) & 31];
  }
  return out;
}

/** Decode into exactly `expectedLength` bytes; throws on any irregularity. */
export function crockfordDecode(text: string, expectedLength: number): Uint8Array {
  const cleaned = text.replace(/[-\s]/g, '');
  const out = new Uint8Array(expectedLength);
  let acc = 0;
  let bits = 0;
  let idx = 0;
  for (const ch of cleaned) {
    const v = DECODE_MAP[ch];
    if (v === undefined) throw new Error(`Invalid Base32 character "${ch}".`);
    acc = (acc << 5) | v;
    bits += 5;
    if (bits >= 8) {
      if (idx >= expectedLength) throw new Error('Base32 input too long.');
      out[idx++] = (acc >>> (bits - 8)) & 0xff;
      bits -= 8;
    }
  }
  if (idx !== expectedLength) throw new Error('Base32 input too short.');
  // Remaining bits are right-pad bits and must be zero.
  if (bits > 0 && (acc & ((1 << bits) - 1)) !== 0) {
    throw new Error('Non-zero Base32 padding bits.');
  }
  return out;
}

/** Group a string into blocks of four characters separated by hyphens. */
export function groupBy4(s: string): string {
  return s.match(/.{1,4}/g)?.join('-') ?? '';
}
