/**
 * Generic Reed-Solomon engine over GF(2^8), primitive polynomial 0x11D.
 *
 * This module provides field arithmetic and generic encode/decode machinery.
 * Protocol profiles are pinned by callers.
 *
 * The current CloakVault v3 wire protocol profile is RS(83,49) with 34
 * parity bytes, defined by `artifacts/cloakvault/docs/cloakvault-protocol-v3.md` §3.
 *
 * Legacy v1 RS(121,93) behavior may remain for historical regression tests
 * but is not a current profile (see legacy-rs121-93-spec.md, historical only).
 *
 * Primitive polynomial: 0x11D (x^8 + x^4 + x^3 + x^2 + 1)
 * Generator roots: α^0, α^1, ..., α^(parity-1)
 * Systematic form: codeword = data || parity
 *
 * ── Polynomial convention ────────────────────────────────────────────────────
 * The ENCODING path uses "MSB-first" (array[0] = highest-degree coefficient)
 * and evaluates via Horner's method treating array[0] as the highest power.
 * This is consistent with the codeword layout: codeword[j] is the coefficient
 * of x^{n-1-j}, so an error at codeword position p contributes:
 *
 *   e_p * (α^i)^{n-1-p}  to syndrome S_i
 *
 * Defining X_p = α^{n-1-p}, we get S_i = Σ e_p * X_p^i (power-sum syndromes).
 *
 * The DECODING path (BM, Chien, Forney) uses "LSB-first" (array[0] = constant
 * term) for locator and evaluator polynomials.  All locator roots are of the
 * form X_p^{-1} = α^{-(n-1-p)}.  The Chien search evaluates at α^{-j}
 * (EXP[255-j] for j = 0..n-1); a root at j means original position n-1-j.
 */

// ── GF(2^8) field tables ──────────────────────────────────────────────────────

const PRIM_POLY = 0x11d; // x^8 + x^4 + x^3 + x^2 + 1

const EXP = new Uint8Array(512);
const LOG = new Uint8Array(256);

(function buildTables() {
  let x = 1;
  for (let i = 0; i < 255; i++) {
    EXP[i] = x;
    LOG[x] = i;
    x <<= 1;
    if (x & 0x100) x ^= PRIM_POLY;
  }
  for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255];
  EXP[255] = 1;
})();

export function gfMul(a: number, b: number): number {
  if (a === 0 || b === 0) return 0;
  return EXP[(LOG[a] + LOG[b]) % 255];
}

export function gfDiv(a: number, b: number): number {
  if (b === 0) throw new Error('GF division by zero');
  if (a === 0) return 0;
  return EXP[(LOG[a] - LOG[b] + 255) % 255];
}

export function gfPow(x: number, n: number): number {
  if (n === 0) return 1;
  if (x === 0) return 0;
  return EXP[(LOG[x] * (n % 255) + 255 * 10) % 255];
}

export function gfInverse(x: number): number {
  if (x === 0) throw new Error('GF inverse of zero');
  return EXP[255 - LOG[x]];
}

// ── Polynomial arithmetic (index 0 = constant term = coeff of x^0) ───────────
type Poly = number[];

function polyAdd(a: Poly, b: Poly): Poly {
  const r: Poly = new Array(Math.max(a.length, b.length)).fill(0);
  for (let i = 0; i < a.length; i++) r[i] ^= a[i];
  for (let i = 0; i < b.length; i++) r[i] ^= b[i];
  return r;
}

function polyScale(p: Poly, s: number): Poly {
  return p.map((c) => gfMul(c, s));
}

function polyShift(p: Poly, deg: number): Poly {
  const r: Poly = new Array(p.length + deg).fill(0);
  for (let i = 0; i < p.length; i++) r[i + deg] = p[i];
  return r;
}

function polyMul(a: Poly, b: Poly): Poly {
  const r: Poly = new Array(a.length + b.length - 1).fill(0);
  for (let i = 0; i < a.length; i++)
    for (let j = 0; j < b.length; j++) r[i + j] ^= gfMul(a[i], b[j]);
  return r;
}

/** Evaluate p[0] + p[1]*x + p[2]*x^2 + ... at x. */
function polyEval(p: Poly, x: number): number {
  let val = 0;
  for (let i = p.length - 1; i >= 0; i--) val = gfMul(val, x) ^ p[i];
  return val;
}

/** Formal derivative over GF(2^8): d/dx(x^n) = n*x^{n-1}; only odd-n terms survive. */
function polyDeriv(p: Poly): Poly {
  const r: Poly = [];
  for (let i = 1; i < p.length; i++) r.push(i % 2 === 1 ? p[i] : 0);
  return r;
}

// ── Syndrome computation ──────────────────────────────────────────────────────
/**
 * S_i = codeword(α^i) using Horner's method with codeword[0] = highest-degree
 * coefficient. An error at position p contributes e_p * (α^i)^{n-1-p}.
 * Defining X_p = α^{n-1-p}: S_i = Σ_p e_p * X_p^i (standard power-sum form).
 */
function calcSyndromes(received: Uint8Array, parity: number): Poly {
  const S: Poly = [];
  for (let i = 0; i < parity; i++) {
    let val = 0;
    for (const b of received) val = gfMul(val, EXP[i]) ^ b;
    S.push(val);
  }
  return S;
}

// ── Generator polynomial ──────────────────────────────────────────────────────
const GENERATOR_CACHE = new Map<number, Uint8Array>();

function buildGeneratorMSB(parity: number): Uint8Array {
  if (GENERATOR_CACHE.has(parity)) return GENERATOR_CACHE.get(parity)!;
  // MSB-first: [1] * (x + α^0) * (x + α^1) * ...
  let g = new Uint8Array([1]);
  for (let i = 0; i < parity; i++) {
    const root = EXP[i];
    const factor = new Uint8Array([1, root]); // x + α^i in MSB-first
    const ng = new Uint8Array(g.length + 1);
    for (let j = 0; j < g.length; j++) ng[j] ^= g[j];
    for (let j = 0; j < g.length; j++) ng[j + 1] ^= gfMul(g[j], root);
    g = ng;
  }
  GENERATOR_CACHE.set(parity, g);
  return g;
}

// ── Parity calculation ────────────────────────────────────────────────────────
/**
 * LEGACY v1 — not part of the current v3 RS(83,49) profile.
 * The retired v1 profile derived parity as ceil(30% of k). Retained only so
 * historical regression tests can pin the v1 numbers explicitly.
 */
export function legacyV1Parity30Pct(k: number): number {
  return Math.ceil(0.3 * k);
}

// ── Encoding ──────────────────────────────────────────────────────────────────
/**
 * Encode k data bytes into a systematic (n = k + parity) codeword.
 * Layout: data[0..k-1] || parity[0..parity-1] (parity appended MSB-first).
 * Parity MUST be supplied explicitly by the caller (profiles are pinned by
 * callers; there is no implicit default).
 */
export function rsEncode(data: Uint8Array, parity: number): Uint8Array {
  return _encode(data, parity);
}

function _encode(data: Uint8Array, p: number): Uint8Array {
  const k = data.length;
  const n = k + p;
  const g = buildGeneratorMSB(p); // g[0]=1 (leading, x^p term), g[p]=constant term
  // rem[j] = coefficient of x^j in remainder polynomial (0=constant, p-1=highest)
  const rem = new Uint8Array(p);
  for (let i = 0; i < k; i++) {
    const feedback = data[i] ^ rem[p - 1]; // top of shift register
    for (let j = p - 1; j > 0; j--) {
      rem[j] = rem[j - 1] ^ gfMul(g[p - j], feedback); // g[p-j] = coeff of x^j
    }
    rem[0] = gfMul(g[p], feedback); // g[p] = constant term of g
  }
  const codeword = new Uint8Array(n);
  codeword.set(data, 0);
  // Parity: rem[p-1] (highest) first, rem[0] (constant) last.
  for (let j = 0; j < p; j++) codeword[k + j] = rem[p - 1 - j];
  return codeword;
}

export const rsEncodeImpl = _encode;

// ── Error/Erasure decoder ─────────────────────────────────────────────────────

export class RSUncorrectable extends Error {
  constructor(msg = 'uncorrectable RS error') { super(msg); this.name = 'RSUncorrectable'; }
}

/**
 * Build the erasure locator polynomial (LSB-first / index-0=constant).
 * For an error at codeword position pos in an n-symbol codeword:
 *   X_{pos} = α^{n-1-pos}  (the "X" value for Forney)
 *   Locator factor = (1 - X_{pos} * x) = (1 + α^{n-1-pos} * x)
 *                  = [1, EXP[n-1-pos]] in constant-first form.
 * The locator has roots at X_{pos}^{-1} = α^{-(n-1-pos)}.
 * Chien variable j = n-1-pos → original position = n-1-j.
 */
function buildErasureLoc(erasurePositions: number[], n: number): Poly {
  let loc: Poly = [1];
  for (const pos of erasurePositions) {
    const alpha_exp = (n - 1 - pos + 255 * 100) % 255; // n-1-pos, always ≥ 0
    loc = polyMul(loc, [1, EXP[alpha_exp]]);
  }
  return loc;
}

/**
 * Berlekamp-Massey on the syndrome sequence S[0..m-1].
 * Returns error locator Λ(x) in LSB-first form such that
 * Σ_{i=0}^{L} Λ[i] * S[j-i] = 0 for j = L..m-1.
 */
function berlekampMassey(S: Poly): Poly {
  let C: Poly = [1]; // current connection polynomial
  let B: Poly = [1]; // previous
  let L = 0, m = 1, b = 1;

  for (let n = 0; n < S.length; n++) {
    let d = S[n];
    for (let i = 1; i <= L && i < C.length; i++) d ^= gfMul(C[i], S[n - i] ?? 0);

    if (d === 0) { m++; continue; }

    const T = C.slice();
    const coef = gfMul(d, gfInverse(b));
    // C = C XOR coef * x^m * B
    C = polyAdd(C, polyScale(polyShift(B, m), coef));

    if (2 * L <= n) { L = n + 1 - L; B = T; b = d; m = 1; } else { m++; }
  }
  return C;
}

/**
 * Decode a received n-byte codeword, correcting up to `parity` errata
 * symbols (2t + e ≤ parity). Returns k = n - parity data bytes.
 *
 * erasurePositions: indices in the received codeword that are known-erased.
 * All failure modes throw RSUncorrectable.
 */
export function rsDecode(
  received: Uint8Array,
  parity: number,
  erasurePositions: number[] = [],
): Uint8Array {
  const n = received.length;
  const k = n - parity;
  const numErasures = erasurePositions.length;

  if (numErasures > parity) throw new RSUncorrectable('too many erasures declared');

  // Fast path: all syndromes zero → no errors.
  const S = calcSyndromes(received, parity);
  if (S.every((v) => v === 0)) return received.slice(0, k);

  // ── Erasure locator ────────────────────────────────────────────────────────
  const erasureLoc: Poly = buildErasureLoc(erasurePositions, n);

  // ── Modified syndromes: T = S * Λ_e (truncated to `parity` terms) ─────────
  // T[i] for i ≥ numErasures should be 0 for pure erasures (no errors).
  // BM is run on T[numErasures .. parity-1] to find only the ERROR locator.
  const T_full = polyMul(S, erasureLoc).slice(0, parity);
  const T_for_BM = T_full.slice(numErasures, parity);

  // ── BM on modified syndromes ───────────────────────────────────────────────
  const errLoc = berlekampMassey(T_for_BM);
  const numErrors = errLoc.length - 1;

  if (2 * numErrors + numErasures > parity) {
    throw new RSUncorrectable('exceeds correction capacity');
  }

  // ── Combined locator ───────────────────────────────────────────────────────
  const combinedLoc: Poly = polyMul(errLoc, erasureLoc);
  const totalExpected = combinedLoc.length - 1;

  // ── Chien search ───────────────────────────────────────────────────────────
  // Evaluate combinedLoc at α^{-j} = EXP[255-j] for j = 0..n-1.
  // A root at j means a codeword error/erasure at original position n-1-j.
  const chienPositions: number[] = []; // Chien variable j values
  for (let j = 0; j < n; j++) {
    if (polyEval(combinedLoc, EXP[(255 - j + 255) % 255]) === 0) {
      chienPositions.push(j);
    }
  }
  if (chienPositions.length !== totalExpected) {
    throw new RSUncorrectable('Chien search: root count mismatch');
  }

  // Verify that the declared erasures are among the found roots.
  // Erasure at original pos → Chien variable j = n-1-pos.
  const foundJ = new Set(chienPositions);
  for (const ep of erasurePositions) {
    const expectedJ = n - 1 - ep;
    if (!foundJ.has(expectedJ)) {
      throw new RSUncorrectable('erasure position not found in Chien search');
    }
  }

  // ── Forney algorithm ───────────────────────────────────────────────────────
  // Ω(x) = S(x) * Λ(x) mod x^parity  (errata evaluator, LSB-first)
  const omega: Poly = polyMul(S, combinedLoc).slice(0, parity);
  const LDeriv: Poly = polyDeriv(combinedLoc);

  const corrected = received.slice();
  for (const j of chienPositions) {
    const X = EXP[j];           // X_p = α^{n-1-pos} = α^j
    const Xinv = EXP[(255 - j + 255) % 255]; // X^{-1} = α^{-j}

    const omega_val = polyEval(omega, Xinv);
    const deriv_val = polyEval(LDeriv, Xinv);
    if (deriv_val === 0) throw new RSUncorrectable('Forney: zero derivative');

    const magnitude = gfMul(X, gfDiv(omega_val, deriv_val));
    const origPos = n - 1 - j;
    corrected[origPos] ^= magnitude;
  }

  // ── Verify ─────────────────────────────────────────────────────────────────
  const S2 = calcSyndromes(corrected, parity);
  if (!S2.every((v) => v === 0)) {
    throw new RSUncorrectable('post-correction syndrome check failed');
  }

  return corrected.slice(0, k);
}

// ── Interleaving — LEGACY v1, not part of the current v3 RS(83,49) profile ───
// Retained for historical regression tests and legacy decoding capability
// only. The v3 wire protocol does not interleave.

function gcd(a: number, b: number): number {
  while (b) { [a, b] = [b, a % b]; }
  return a;
}

function modInverse(a: number, m: number): number {
  let [old_r, r] = [a, m];
  let [old_s, s] = [1, 0];
  while (r !== 0) {
    const q = Math.floor(old_r / r);
    [old_r, r] = [r, old_r - q * r];
    [old_s, s] = [s, old_s - q * s];
  }
  return ((old_s % m) + m) % m;
}

export function interleaveParams(n: number): { stride: number; invStride: number } {
  let stride = Math.max(1, Math.floor(Math.sqrt(n)));
  while (gcd(stride, n) !== 1) stride++;
  return { stride, invStride: modInverse(stride, n) };
}

export function interleave(codeword: Uint8Array): Uint8Array {
  const n = codeword.length;
  const { stride } = interleaveParams(n);
  const out = new Uint8Array(n);
  for (let i = 0; i < n; i++) out[i] = codeword[(i * stride) % n];
  return out;
}

export function deinterleave(interleaved: Uint8Array): Uint8Array {
  const n = interleaved.length;
  const { invStride } = interleaveParams(n);
  const out = new Uint8Array(n);
  for (let i = 0; i < n; i++) out[i] = interleaved[(i * invStride) % n];
  return out;
}

/** LEGACY v1 — not part of the current v3 RS(83,49) profile. */
export function rsEncodeInterleaved(data: Uint8Array, parity: number): Uint8Array {
  return interleave(_encode(data, parity));
}

/**
 * LEGACY v1 — not part of the current v3 RS(83,49) profile.
 * Deinterleave and RS-decode.
 * erasurePositionsInterleaved: indices in the interleaved sequence known to be erased.
 * Maps to codeword positions before passing to rsDecode.
 */
export function rsDecodeInterleaved(
  received: Uint8Array,
  parity: number,
  erasurePositionsInterleaved: number[] = [],
): Uint8Array {
  const n = received.length;
  const { stride } = interleaveParams(n);
  // interleaved[i] = codeword[(i * stride) % n]
  // → interleaved position p → codeword position (p * stride) % n
  const cwErasures = erasurePositionsInterleaved.map((p) => (p * stride) % n);
  const codeword = deinterleave(received);
  return rsDecode(codeword, parity, cwErasures);
}
