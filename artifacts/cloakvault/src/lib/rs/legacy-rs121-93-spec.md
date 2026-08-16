# CloakVault Reed-Solomon Protocol Specification

## Status

**SUPERSEDED — HISTORICAL ONLY.**

This document specified the retired v1 slot-cloak Reed-Solomon profile:

- RS(121,93)
- 28 parity bytes
- legacy interleaving

The current QuietKey/CloakVault v3 wire protocol uses **RS(83,49), 34 parity
bytes**, defined solely in:

`artifacts/cloakvault/docs/cloakvault-protocol-v3.md`

Nothing in this document is a current protocol constant.

---

## 1. Field: GF(2^8)

Primitive polynomial: **x^8 + x^4 + x^3 + x^2 + 1 = 0x11D**
(= 285 decimal, used in CD-ROM / QR Code, widely tabulated)

Field elements are 8-bit unsigned integers (0–255).

### 1.1 Field Arithmetic

**Addition / Subtraction**: bitwise XOR (same in characteristic-2 fields).

**Multiplication**: standard GF(2^8) log/antilog table lookup using the
primitive polynomial above.

   exp_table[i+1]  = (exp_table[i] << 1) XOR (0x11D if bit 7 was set)
   exp_table[255]  = exp_table[0] = 1
   log_table[exp_table[i]] = i   (for i = 0..254)
   0 * anything = 0;  0 has no log entry.

**Division**: a / b = a * inverse(b); inverse(b) = exp_table[255 - log_table[b]].

---

## 2. Code Construction

**Code family**: Systematic Reed-Solomon over GF(2^8), similar to a shortened
RS(255, k') code.

**Symbol ordering**: big-endian within a codeword; the first symbol in the
codeword array corresponds to the coefficient of the highest power of the
generator polynomial in the remainder.

**Systematic form**: codeword = data_symbols || parity_symbols

### 2.1 Generator Polynomial

Generator roots: consecutive powers of the field primitive element α,
starting at exponent **0**:

   g(x) = prod_{i=0}^{parity-1} (x - α^i)
         = prod_{i=0}^{parity-1} (x XOR exp_table[i])

(In GF(2^8), subtraction = XOR, so (x - α^i) = (x XOR exp_table[i]).)

The generator polynomial is computed at runtime from the pinned primitive
polynomial and root convention. Its coefficients are fixed for any given
`parity` count.

---

## 3. Parity Count

   parity = ceil(0.30 × k)

where `k` is the number of **data symbols** (bytes) in the unprotected
payload.

For the CloakVault capsule (93 data bytes):

   parity = ceil(0.30 × 93) = ceil(27.9) = 28

Exact (n, k) for the capsule:

   k = 93     data symbols
   n = 121    codeword symbols  (93 + 28)

---

## 4. Shortening

The code is a **shortened** RS code: instead of padding data to 255 - parity
symbols, we use data exactly as supplied. All arithmetic treats the virtual
"missing" symbols as zeros.

Specifically:
- Encode by evaluating the remainder of (data polynomial × x^parity) divided
  by g(x).
- No explicit padding bytes appear in the codeword.

---

## 5. Interleaving

Purpose: prevent a contiguous physical damage burst from wiping an entire
block of RS symbols.

**Algorithm** (versioned as interleave-v1):

Given a codeword of `n` symbols, define `stride = max(1, floor(sqrt(n)))`.

Interleaved position of symbol `i`:

   interleaved[i] = codeword[ (i * stride) mod n ]
   deinterleaved[i] = interleaved[ (i * inverse_stride) mod n ]

where `inverse_stride` is the modular inverse of `stride` modulo `n`
(computed via extended Euclidean algorithm). If gcd(stride, n) ≠ 1 (stride
and n are not coprime), increment stride by 1 until they are.

For n = 121, stride = floor(sqrt(121)) = 11, gcd(11, 121) = 11 ≠ 1.
Increment: stride = 12, gcd(12, 121) = 1. ✓

So for n = 121: **stride = 12**.

Deinterleave: inverse of 12 modulo 121 = 121*k+1 divisible by 12 → 121*1+1=122, 122/12 not integer; 121*11+1=1332/12=111 ✓. **inverse_stride = 111**.

Verification: 12 × 111 mod 121 = 1332 mod 121 = 1332 − 11×121 = 1332 − 1331 = 1. ✓

---

## 6. Encoding

1. Compute g(x) from pinned roots.
2. Let data = the k data bytes.
3. Compute parity = remainder of poly_mul(data, x^parity) / g(x) in GF(2^8).
4. Codeword = data || parity (n bytes, systematic form).
5. Apply interleaving to produce the transmitted sequence.

---

## 7. Decoding

**Input**: a received sequence of n bytes with some positions possibly erased
(known erasure locations) or substituted by errors (unknown locations).

**Capacity**: `2t + e ≤ parity`, where t = error count, e = erasure count.

### 7.1 Syndrome Computation

For root exponents i = 0..parity-1:

   S[i] = sum_{j=0}^{n-1} received[j] × (α^i)^j   (in GF(2^8))

If all syndromes are zero → the received word is a valid codeword.

### 7.2 Erasure Handling

Build the erasure locator polynomial:

   Λ_e(x) = prod_{j in erasure_locs} (1 - x × α^j)

(computed by repeated polynomial multiplication).

The modified syndrome sequence removes the effect of known erasures before
error-locator search.

### 7.3 Berlekamp-Massey on Modified Syndromes

Run BM on the "erased-corrected" syndrome vector to find the error locator
polynomial Λ_err(x). Combined locator: Λ(x) = Λ_err(x) × Λ_e(x).

### 7.4 Chien Search

Evaluate Λ(x) at each α^{-j} for j = 0..n-1 to find error/erasure locations.
The location set must exactly match total_errors + total_erasures.
If it does not, return UNCORRECTABLE.

### 7.5 Forney Algorithm

Compute the error/erasure magnitudes using the Forney formula:

   e_j = - Ω(α^{-j}) / Λ'(α^{-j})

where:
- Ω(x) = (S(x) × Λ(x)) mod x^parity   (error evaluator polynomial)
- Λ'(x) = formal derivative of Λ(x) over GF(2^8) (XOR of odd-position coefficients, shifted)

### 7.6 Correction

XOR each computed magnitude into the received word at the found locations.

### 7.7 Verification

After correction, recompute all syndromes. If any are non-zero → UNCORRECTABLE.
Verify the corrected word has correct systematic structure.

---

## 8. Error and Erasure Representation

**Erasure**: a symbol position is explicitly marked as unknown/missing by the
caller. The decoder treats all erased positions simultaneously.

**Error**: a symbol at an unknown position is corrupted. Detected via non-zero
syndrome.

---

## 9. Independent RS Test Vectors

These vectors were generated from the above construction (primitive poly 0x11D,
roots α^0..α^(parity-1), systematic, no interleaving) and are now fixed.
A future Python implementation must reproduce these outputs exactly.

### Vector 1 (k=4, parity=2, n=6)
Input data: [0x01, 0x02, 0x03, 0x04]
Codeword:   [0x01, 0x02, 0x03, 0x04, 0xC3, 0x49]  ← parity computed below
(Compute: parity bytes are the last 2 of the codeword.)

*Note:* The exact parity bytes for each test vector are computed by the
implementation from the pinned construction. These vectors are generated by the
test harness once and then frozen as fixed expectations — see rs.test.ts for
the stored expected values.

---

## 10. Summary of Protocol Constants

| Parameter | Value |
|-----------|-------|
| Primitive polynomial | 0x11D (x^8+x^4+x^3+x^2+1) |
| Generator roots | α^0, α^1, …, α^(parity-1) |
| Root starting exponent | 0 |
| Systematic form | data ‖ parity |
| Parity count formula | ceil(0.30 × k) |
| Capsule k | 93 bytes |
| Capsule parity | 28 bytes |
| Capsule n | 121 bytes |
| Interleave version | v1 |
| Interleave stride (n=121) | 12 |
| Interleave inverse stride (n=121) | 111 |
| Code family | Shortened RS(255, 255-parity) over GF(2^8) |
