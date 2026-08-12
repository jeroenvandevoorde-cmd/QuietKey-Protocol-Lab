# CloakVault Protocol v3 — Frozen Specification (capsule version 0x02)

**Status: FROZEN.** Every constant in this document is fixed for capsule version
`0x02`. Any future change takes a new version byte and a new specification;
capsules of earlier versions remain decodable by their own rules (§7).

**Audience and bar:** a competent engineer, given only this document and no
access to the source code, must be able to reimplement an encoder and decoder
that interoperate **byte-for-byte** with the reference implementation. A
machine-readable conformance vector accompanies this spec at
`docs/cloakvault-v3-test-vector.json` (regenerated from the reference
implementation by `scripts/generate-spec-vector.ts`); §6 narrates it.

> **TEST USE ONLY.** This is an experimental reference protocol. All secrets in
> this document and in the vector file are published test secrets. Never reuse
> them, and never protect real funds with this implementation.

---

## 1. Overview and data flow

```
24-word BIP39 mnemonic
  → 32-byte seed entropy
  → 49-byte Recovery Capsule            (§2: AES-256-GCM-SIV under the Vault Key)
  → 83-byte Reed–Solomon codeword       (§3: RS(83,49) over GF(2^8), 34 parity bytes)
  → 142-character Bech32 footer token   (§4: sentinel + 133 data chars + 6 checksum chars)
  → printed page footer                 (§5: presentation only; carries the token)
```

Recovery reverses the chain. The printed page's *body* (a recipe) carries
**zero** payload; the token is the only payload channel, and its extraction is
purely structural (§4.4) — it must never depend on the surrounding text.

All multi-byte values in this protocol are byte strings processed in order;
there are no multi-byte integer fields, so no endianness ambiguity arises
except where §4.2 defines bit order explicitly.

## 2. Recovery Capsule (49 bytes)

### 2.1 Byte layout

| offset | length | field | value |
|---|---|---|---|
| 0 | 1 | version | `0x02` (the only version this spec defines) |
| 1 | 32 | ciphertext | AES-256-GCM-SIV ciphertext of the 32-byte seed entropy |
| 33 | 16 | tag | AES-256-GCM-SIV authentication tag, full length, never truncated |

Total: exactly **49 bytes**. Decoders MUST reject any other length and MUST
reject a version byte other than `0x02` before attempting decryption.

### 2.2 Cipher

`AEAD_AES_256_GCM_SIV` as specified in **RFC 8452**, exactly as published
(little-endian POLYVAL conventions etc. are internal to RFC 8452; implement or
use a library that passes the RFC 8452 Appendix C.2 known-answer tests — the
reference test suite pins four of them: empty plaintext, 16-byte plaintext,
32-byte plaintext, and the 8-byte-plaintext/1-byte-AAD case, all with the
AES-256 key `0100…00` and nonce `030000000000000000000000`).

- **Plaintext:** the 32-byte BIP39 seed entropy (entropy, not the 64-byte
  BIP39 seed).
- **AAD:** exactly one byte, the version prefix `0x02` (hex `02`). This binds
  the version cryptographically: flipping the version byte fails
  authentication rather than reaching a different parse path.
- **Nonce:** fixed all-zero 12 bytes, hex `000000000000000000000000`. The
  nonce is NOT stored in the capsule.

### 2.3 Deterministic-equality property (INTENDED — do not "fix")

Because the nonce is fixed and the key derivation (§2.4) is deterministic,
**the identical seed entropy under the identical Vault Key produces a
byte-identical capsule.** This is an intended, load-bearing property: it makes
independently produced "equivalent cards" for the same seed+key carry the same
payload, so any one of them recovers the wallet and they can be
cross-verified. Under RFC 8452's nonce-misuse resistance, the only leak is
*equality* of (seed, key) pairs. A future maintainer MUST NOT introduce a
random or stored nonce for version `0x02`; that would silently break card
equivalence. Any design that wants randomness takes a new version byte.

### 2.4 Key derivation

```
capsuleKey = HKDF-SHA256(
    ikm  = Vault Key            (exactly 32 bytes, full-entropy),
    salt = empty                (the ZERO-LENGTH byte string; per RFC 5869 §2.2
                                 this is equivalent to a salt of HashLen=32 zero
                                 bytes fed to HMAC — but conformant
                                 implementations pass a zero-length salt),
    info = ASCII "CLOAKVAULT-V3-CAPSULE-KEY"
           = hex 434c4f414b5641554c542d56332d43415053554c452d4b4559  (25 bytes,
             no terminator, no length prefix),
    L    = 32 bytes
)
```

The Vault Key is a uniformly random 256-bit key. Its human transcription
format (`CVK1.` + Crockford Base32 with checksum) is unchanged from v1 and out
of scope here; the capsule layer consumes the raw 32 bytes.

### 2.5 Failure behavior

Wrong key, altered version/ciphertext/tag, or malformed length MUST all
produce the same typed failure with **no partial plaintext ever released**.

## 3. Reed–Solomon layer — RS(83, 49) over GF(2^8)

### 3.1 Field

GF(2^8) with primitive polynomial **`0x11D`** (x⁸ + x⁴ + x³ + x² + 1),
generator element α = `0x02`. Bytes map to field symbols identically (byte
value = field element).

### 3.2 Code

- **n = 83, k = 49, parity = 34.** (Data = the 49-byte capsule.)
- **Generator polynomial:** g(x) = ∏ᵢ₌₀³³ (x − αⁱ) — roots are consecutive
  powers **α⁰ … α³³** (first consecutive root = α⁰ = 1).
- **Systematic:** `codeword = data[0..48] ‖ parity[0..33]`. The parity bytes
  are the remainder of `data(x)·x³⁴ mod g(x)`, appended **highest-degree
  remainder coefficient first** (i.e. `codeword[49]` is the coefficient of
  x³³ of the remainder, `codeword[82]` the constant term).
- **Position convention:** `codeword[j]` is the coefficient of `x^(n−1−j)`;
  syndromes are Sᵢ = Σₚ eₚ·(α^(n−1−p))^i for i = 0..33. (Any standard
  errors-and-erasures decoder — Berlekamp–Massey/Euclidean + Chien + Forney —
  works once these conventions are fixed.)

> **Non-normative note (Forney error magnitude — convenience derivation).**
> This note is a derivation aid only; it adds no requirement beyond the
> conventions above. With the first consecutive root α⁰ (i.e. b = 0), the
> syndrome polynomial S(x) = S₀ + S₁x + … + S₃₃x³³, the error/erasure
> locator Λ(x) with roots at Xₚ⁻¹ where Xₚ = α^(n−1−p) for each corrupt
> position p, and the evaluator Ω(x) = S(x)·Λ(x) mod x³⁴, the error
> magnitude at position p is:
>
> ```
> e_p = X_p · Ω(X_p⁻¹) / Λ′(X_p⁻¹)
> ```
>
> where Λ′ is the formal derivative of Λ (in GF(2⁸): the odd-degree terms of
> Λ with exponents reduced by one). The leading `X_p` factor is a consequence
> of b = 0; codes with b = 1 omit it. Any algebraically equivalent
> formulation is equally conformant.

### 3.3 Correction budget and erasure interface

```
2 · (number of error bytes) + (number of erasure bytes) ≤ 34
```

- **Erasures** are codeword byte positions declared unreadable by the caller,
  passed to the decoder as an explicit list of indices `0..82`. Erased byte
  values are irrelevant (conventionally 0).
- **Errors** are wrong bytes at unknown positions; the decoder locates them.
- The decoder MUST fail cleanly (no output) when the budget is exceeded, and
  SHOULD report the number of erasures used and errors corrected on every
  attempt.

### 3.4 Reader conformance rule (protocol-level, binding)

**Any conformant reader — human, app, or device — MUST mark an uncertain or
degraded character as an erasure and MUST NOT emit a confident guess.**
An erasure costs 1 parity byte; a wrong guess costs 2. Empirically this rule
is the difference between catastrophic and safe behavior under physical
damage. This governs correctness, not UX: an implementation that guesses at
damaged characters is non-conformant even if it sometimes succeeds.

## 4. Bech32 footer token

### 4.1 Alphabet

```
value:   0123456789...                        31
char :   q p z r y 9 x 8 g f 2 t v d w 0 s 3 j n 5 4 k h c e 6 m u a 7 l
```

Exactly the Bech32 charset of BIP-173: `qpzry9x8gf2tvdw0s3jn54khce6mua7l`.
The string index of each character **is** its 5-bit value (`q`=0 … `l`=31).
Tokens are written lowercase; decoders MUST accept uppercase by lowercasing
first (never mixed-case-sensitive).

### 4.2 Byte → character packing

The 83 codeword bytes form a 664-bit string, **most significant bit of byte 0
first**. Read 5 bits at a time, MSB-first, producing 5-bit values; each value
indexes the alphabet. 664 = 132·5 + 4, so the 133rd (final) data character
carries the last 4 bits **padded with a single 0 bit on the right** (i.e.
`lastValue = (last4bits << 1)`). Decoders reverse this: 133 chars → 665 bits →
drop the final pad bit → 83 bytes. Decoders SHOULD ignore the pad bit's value
rather than rejecting a nonzero pad (an erased final character already maps to
byte erasures).

### 4.3 Token structure

```
token = "cv0" ‖ data(133 chars) ‖ checksum(6 chars)      — 142 characters total
```

- **Sentinel `cv0`:** a fixed 3-character prefix drawn from the alphabet. It
  is purely structural — a locator, not data; it does not participate in the
  checksum and is not part of the 83-byte codeword.
- **Checksum:** the standard **Bech32 BCH checksum of BIP-173** ("bech32",
  XOR constant `1` — not Bech32m), computed with human-readable part
  **`"cv"`** over the 133 data values:
  `checksum = bech32_create_checksum(hrp="cv", data=values[0..132])` exactly
  per BIP-173's `polymod`/`hrp_expand` reference algorithm (generator
  constants `0x3b6a57b2, 0x26508e6d, 0x1ea119fa, 0x3d4233dd, 0x2a1462b3`).
  It detects any single-character substitution with certainty and any burst
  of ≤ 4 characters. Note the HRP `"cv"` is a checksum input only; it never
  appears in the token — the printed prefix is the sentinel `cv0`.
- The checksum is advisory triage: if it verifies, the token is intact
  (skip straight to RS); if not, corruption exists and RS decoding proceeds.
  Erasure marks make the checksum unverifiable; report that state distinctly.

### 4.4 Extraction (genre-independence, binding)

Extraction from pasted/scanned text is **purely structural** and MUST NOT
depend on the surrounding URL, domain name, parameter names, or any body
text:

1. Lowercase the input and strip ALL whitespace (line wrapping is
   presentation only, §5).
2. Consider maximal runs of characters that are in the alphabet or are the
   erasure mark `?`.
3. **Sentinel rule:** if a run contains `cv0` with ≥ 142 characters from that
   point, the token is the 142 characters starting at the sentinel.
4. **Fallback (sentinel destroyed):** otherwise, any run of ≥ 142 such
   characters; take its trailing 142 characters.

Unreadable characters are marked `?` by the reader (per §3.4). Each `?` maps
to erasures on **every codeword byte its 5 bits overlap** (one or two bytes).

## 5. Rendered footer (presentation only)

The token is printed inside a fake "browser print exhaust" footer, wrapped at
**48 characters per line**, e.g.:

```
https://arecipeforamaster.com/print?id=cv0qfwk4fu0e0d7sjsvht7nhssh3avu9h4cj8lahkfwqq73t
uewewr93j3v2earx3n7valzh34stw6e9u543elpx9aj8es
dh974sk9f9pxdfj9apsfe95x5g8eh8xugmjphs87n64gtxpc&v=1
Printed 12/08/2026 · page 1 of 1
```

The URL, domain, `id=`/`&v=1` dressing, date line, and the 48-char wrap are
**not part of the payload** and MUST NOT be relied on by decoders (§4.4). The
page body (a recipe) carries zero payload; body and token are fully
independent.

## 6. End-to-end conformance vector (worked example)

Machine-readable copy: `docs/cloakvault-v3-test-vector.json`. **Published
test secrets — never reuse.**

| quantity | value |
|---|---|
| seed entropy (32B) | `000102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f` |
| mnemonic | `abandon amount liar amount expire adjust cage candy arch gather drum bullet absurd math era live bid rhythm alien crouch range attend journey unaware` |
| Vault Key (32B) | `202122232425262728292a2b2c2d2e2f303132333435363738393a3b3c3d3e3f` |
| Vault Key text | `CVK1.04G2-28H3-4GJJ-C9S8-54N2-PB1D-5RQK-0C9J-6CT3-ADHQ-70WK-MESW-7MZ3-Y8AM-SQAG` |
| HKDF info (hex) | `434c4f414b5641554c542d56332d43415053554c452d4b4559` |
| derived AES key | `99f34c91a3538dd53d25bfbd13fe2544fede0197ea1aceec7aeabf915c0c3eda` |
| capsule (49B) | `025d6aa78fcbdbe84a0cbafd3bc2178f59c2deb891ffdbd92e003d15f32ecb8658ca2c567a33467e677e2bc6b05bb592f2` |
| RS parity (34B) | `958e7e1317b23e60db97d5858a9284cd4c8bd0c1392d0d441f3739b88dc83781fd3d` |
| codeword (83B) | capsule ‖ parity |
| token (142 chars) | `cv0qfwk4fu0e0d7sjsvht7nhssh3avu9h4cj8lahkfwqq73tuewewr93j3v2earx3n7valzh34stw6e9u543elpx9aj8esdh974sk9f9pxdfj9apsfe95x5g8eh8xugmjphs87n64gtxpc` |
| expected fingerprint | `3E1F-3AE0` (BIP32 master fingerprint of the recovered seed) |
| footer line 1 | `https://arecipeforamaster.com/print?id=cv0qfwk4fu0e0d7sjsvht7nhssh3avu9h4cj8lahkfwqq73t` |

A reimplementation verifies each arrow of §1 against these values, then the
reverse path: token → codeword → capsule → (Vault Key) → entropy → mnemonic →
fingerprint `3E1F-3AE0`. The capsule crypto is independently anchored by the
RFC 8452 Appendix C.2 KATs listed in §2.2.

## 7. Versioning

All constants above are frozen for capsule version `0x02`: the AEAD, the
zero nonce, the HKDF salt/info, the AAD, RS(83,49) with `0x11D` and roots
α⁰…α³³, the alphabet, the sentinel `cv0`, the HRP `"cv"`, and the packing.
Any change — however small — takes a **new version byte and a new spec
document**. Decoders select rules by the version byte; v1 (93-byte
XChaCha20-Poly1305) capsules and v2 (`0x02`) capsules each remain decodable
by their own frozen rules indefinitely.
