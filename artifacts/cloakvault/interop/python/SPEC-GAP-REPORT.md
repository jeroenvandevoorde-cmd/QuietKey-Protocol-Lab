# CloakVault v3 — Spec-Gap Report (Python interop milestone)

**Method:** the Python implementation under `interop/python/` was written from
`docs/cloakvault-protocol-v3.md` and `docs/cloakvault-v3-test-vector.json`
only. The behavioral proof: it reproduces the published token, capsule,
derived key, parity bytes, entropy, and fingerprint byte-for-byte, and
cross-decodes fresh tokens with the TypeScript implementation in both
directions — values it was never handed as answers.

**Result: acceptance criteria 1–2 passed on the first run of the test suite,
with no corrections to any protocol constant, ordering, or bit convention.**

## Points where judgment was exercised (none turned out to be a byte-determining gap)

1. **RS decoder algorithm choice.** The spec (§3.2) fixes all conventions
   (positions, syndromes, roots) but deliberately leaves the decoding
   *algorithm* open ("any standard errors-and-erasures decoder"). Python uses
   Berlekamp–Massey initialized with the erasure locator + Chien + Forney.
   Assumption correct: not a gap — decoding algorithm is implementation
   freedom by design; only the code's algebra is normative.

2. **Forney formula variant.** With first consecutive root α⁰, the magnitude
   formula is `e_p = X_p · Ω(X_p⁻¹) / Λ'(X_p⁻¹)`. The spec does not state
   this formula (it follows mathematically from the §3.2 conventions), and it
   was derived rather than guessed. Correct on first attempt. *Optional
   spec clarification:* a non-normative note giving this formula would save a
   reimplementer the derivation.

3. **Footer URL dressing.** §5 shows the footer format by example
   (`https://arecipeforamaster.com/print?id=…`, `&v=1`, `Printed <date> ·
   page 1 of 1`). Python reproduced the rendered lines from the example and
   the vector's `rendering.footerLines`. Not a protocol gap — §5 explicitly
   declares all dressing presentation-only and non-normative; exact-match
   rendering was only needed to hit acceptance criterion 2's "same rendered
   footer line".

4. **`cryptography` AAD `None` vs `b""`.** The pyca library treats absent AAD
   as `None`; the RFC KATs with zero-length AAD required passing `None`.
   Library detail, not a spec issue (CloakVault's AAD is always the 1-byte
   version prefix).

## Conclusion

**No spec gaps found that left a byte, bit order, constant, or ordering
undetermined.** The specification is sufficient, as written, to produce a
byte-for-byte interoperable independent implementation. No spec changes are
required; item 2 above is proposed as an optional non-normative clarification.

## Libraries

- AES-256-GCM-SIV: `cryptography` (pyca) **50.0.0** — validated in-suite
  against RFC 8452 Appendix C.2 KATs (4 vectors, encrypt + decrypt).
- Everything else (HKDF, RS, Bech32, BIP39 seed, BIP32 fingerprint,
  RIPEMD-160, secp256k1): Python stdlib + pure-Python code written from the
  public standards, no shared code with the app.
