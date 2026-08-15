# Task 1 — Capsule byte-map audit (REPORT ONLY, no code changed)

## Current 93-byte capsule: field-by-field map

| Field | Offset | Size | Purpose | Produced | Consumed |
|---|---|---|---|---|---|
| version | 0 | 1 | Format/derivation-profile marker (0x01) | `capsule.ts` `serializeCapsule` / `CAPSULE_VERSION` | `capsule.ts` `parseCapsule` (strict check), `capsuleAad` (AAD byte 0) |
| generation | 1–4 | 4 (BE) | Key-rotation counter (always 1 in this reference; `INITIAL_GENERATION`) | `capsule.ts` `createCapsule` | `kdf.ts` `deriveCapsuleKey` (HKDF info suffix), `capsule.ts` `capsuleAad`, `parseCapsule` (`readU32be`) |
| capsuleID | 5–20 | 16 | Per-capsule random identifier; HKDF salt; AAD binding | `createCapsule` via injected `rng.randomBytes(16)` | `kdf.ts` `deriveCapsuleKey` (salt), `capsuleAad`, Inspector display via `pipeline.ts` |
| nonce | 21–44 | 24 | XChaCha20-Poly1305 nonce | `createCapsule` via `rng.randomBytes(24)` | `aead.ts` `aeadEncrypt`/`aeadDecrypt` (`xchacha20poly1305`) |
| ciphertext | 45–76 | 32 | Encrypted 32-byte BIP39 seed entropy | `aead.ts` `aeadEncrypt` | `capsule.ts` `openCapsule` → `aeadDecrypt` |
| tag | 77–92 | 16 | Poly1305 authentication tag | `aeadEncrypt` (split from sealed output) | `openCapsule` → `aeadDecrypt` (recombined) |

AAD = capsule bytes 0–20 (version ‖ generation ‖ capsuleID). Not stored anywhere in the
93 bytes: fingerprint (computed from the seed in `pipeline.ts` at create and recover —
`masterFingerprintFromSeed`), key hint (does not exist). Nothing else to flag: the six
fields above account for all 93 bytes exactly.

## Keep-or-drop verdicts against the v2 target (1 + 32 + 16 = 49 bytes)

| Field | Verdict | Justification |
|---|---|---|
| version (1) | **KEEP** | One byte fixes format and implies the derivation profile; cheapest possible misuse guard. |
| ciphertext (32) | **KEEP** | It is the payload. |
| tag (16) | **KEEP full length** | 128-bit authentication is the binary RECOVERY FAILED guarantee; truncation weakens forgery resistance for zero page benefit (16 bytes ≈ 2 rendered slots). |
| nonce (24) | **DROP** | Under an RFC-standardized SIV construction the synthetic IV is derived, not stored; the tag doubles as the IV carrier (RFC 8452) so no stored nonce is needed. |
| KDF salt (capsuleID as salt, 16) | **DROP** | The Vault Key is already a uniformly random 256-bit secret; HKDF with empty/constant salt loses nothing (RFC 5869 §3.1). |
| stored fingerprint | **DROP (never stored)** | Already derived from the seed after decryption; current code confirms it lives outside the capsule. |
| key hint | **DROP (never stored)** | Does not exist in v1 either. |

### Flagged fields not on the target list

- **generation (4 bytes)** — exists solely for key rotation, which is explicitly out of
  scope for this reference; it is constant 1 in every capsule ever produced here. Dropping
  it removes the rotation counter from the wire format: if rotation is ever wanted, it must
  return via the version byte (a new version = new derivation profile) or an external
  convention. What breaks in the reference if removed: only the HKDF `info` suffix and AAD
  layout change — no functional loss.
- **capsuleID (16 bytes)** — beyond its salt role (drop justified above) it currently gives
  each capsule a distinct identity and makes the capsule key per-capsule. Dropping it means
  the v2 key schedule depends only on (Vault Key, version), so a **deterministic** SIV
  encryption of the same seed under the same Vault Key yields a byte-identical capsule.
  That is the defining SIV property (equality leakage, nothing more), but it is a real
  behavioral change: re-creating a document for the same seed+key produces the identical
  codeword, hence an identical-plaintext detector across two captured documents. Stating
  it here as a decision input, not deciding it.

## SIV availability in the current dependency stack

- **RFC 8452 AES-256-GCM-SIV: AVAILABLE.** `@noble/ciphers` 2.3.0 (already a dependency)
  exports `gcmsiv` (`@noble/ciphers/aes.js`), an audited noble implementation. Tag is
  16 bytes, matching the target.
- **RFC 5297 AES-SIV (CMAC-based, fully deterministic): NOT available.** No implementation
  exists in `@noble/ciphers`, `@noble/hashes`, or any other current dependency.
- Plain statement of the consequence: RFC 8452 still *takes* a 96-bit nonce input; it is
  nonce-misuse-*resistant*, not nonce-free. "No stored nonce" therefore means a fixed or
  key/context-derived nonce, which makes encryption deterministic — safe under RFC 8452
  (degrades only to equality leakage), but it is a spec-level choice the owner must pin:
  fixed all-zero nonce vs. HKDF-derived constant. Flagged per the ambiguity rule; no
  choice made here.

## Confirmed v2 numbers

- Byte count: **49** (1 version + 32 ciphertext + 16 tag). Delta from target: **0**.
- Parity at the standing 30% rule (`calcParity(k) = ceil(0.3·k)`): ceil(14.7) = **15** →
  **RS(64, 49)** in the existing GF(2^8) construction.
- Codeword: 64 bytes = **512 bits**.
- Interleave under the existing protocol rule (`interleaveParams`): n = 64, stride =
  smallest s ≥ ⌊√64⌋ with gcd(s, 64) = 1 → **stride 9, invStride 57**.

## Archetype selector bit positions for v2 (proposal only)

Requirement: pin the selector inside the ciphertext region so the constant-archetype bug
(selector reading fixed header bytes) cannot recur. In the v2 layout, ciphertext occupies
capsule bytes 1–32; every one of those bytes is uniformly distributed under any key.

**Proposed spec constants** (mirrors the 0002 fix, which used AEAD ciphertext byte 3):

- Archetype bits = the two MSBs (bits 7, 6) of **capsule byte 4 = AEAD ciphertext byte 3**.
- Under RS(64,49), capsule byte 4 is pre-interleave codeword byte 4 (data symbols first);
  with stride 9 the post-interleave position j satisfies 9j ≡ 4 (mod 64) → j = 4·57 mod 64
  = **interleaved byte 36**, i.e. **transmitted codeword bits 288 and 289**.
- Same mechanism as 0002: pure bit-map permutation via a `templateBitToCodewordBit` analogue,
  zero capacity cost, selector bits re-enter decode as certain data after structural
  archetype detection.

No part of v2 is implemented. This is the audit only.
