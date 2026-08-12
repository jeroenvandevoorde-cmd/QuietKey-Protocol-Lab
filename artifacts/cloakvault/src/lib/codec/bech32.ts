/**
 * Bech32 alphabet + checksum primitive (BIP-173 constants — NOT invented).
 *
 * Charset: "qpzry9x8gf2tvdw0s3jn54khce6mua7l" — deliberately excludes the
 * confusable characters 1, b, i, o.
 *
 * Checksum: the standard Bech32 BCH code (polymod with the BIP-173
 * generator constants, constant 1), computed over the expanded
 * human-readable prefix "cv" plus the 5-bit data values, emitting 6
 * checksum characters. Detects any single-character error with certainty
 * and any burst of up to 4 characters.
 */
export const BECH32_CHARSET = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l';
export const BECH32_HRP = 'cv';

const GEN = [0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3];

export function polymod(values: number[]): number {
  let chk = 1;
  for (const v of values) {
    const top = chk >>> 25;
    chk = ((chk & 0x1ffffff) << 5) ^ v;
    for (let i = 0; i < 5; i++) if ((top >>> i) & 1) chk ^= GEN[i];
  }
  return chk >>> 0;
}

export function hrpExpand(hrp: string): number[] {
  const out: number[] = [];
  for (const c of hrp) out.push(c.charCodeAt(0) >>> 5);
  out.push(0);
  for (const c of hrp) out.push(c.charCodeAt(0) & 31);
  return out;
}

/** 6-character checksum over the HRP + 5-bit data values (Bech32, constant 1). */
export function createChecksum(data: number[]): number[] {
  const values = [...hrpExpand(BECH32_HRP), ...data, 0, 0, 0, 0, 0, 0];
  const mod = polymod(values) ^ 1;
  const out: number[] = [];
  for (let i = 0; i < 6; i++) out.push((mod >>> (5 * (5 - i))) & 31);
  return out;
}

export function verifyChecksum(dataWithChecksum: number[]): boolean {
  return polymod([...hrpExpand(BECH32_HRP), ...dataWithChecksum]) === 1;
}

const CHAR_TO_VAL = new Map<string, number>([...BECH32_CHARSET].map((c, i) => [c, i]));

export function charToValue(c: string): number | undefined {
  return CHAR_TO_VAL.get(c.toLowerCase());
}

export function valueToChar(v: number): string {
  return BECH32_CHARSET[v & 31];
}
