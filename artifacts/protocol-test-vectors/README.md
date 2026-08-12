# CloakVault Protocol Test Vectors

**⚠️ TEST SECRETS ONLY — FOR INTEROPERABILITY TESTING**

These vectors contain the **all-zeros-entropy mnemonic** (23× "abandon" + "art").
This is the CloakVault FIXED_TEST_MNEMONIC, a publicly known test seed.
Never use these values with real funds or on a live wallet.

## Files

| File | Description |
|------|-------------|
| `cloakvault-vectors-v1.json` | Complete protocol vectors (JSON) |
| `capsule.bin` | Raw 93-byte Recovery Capsule binary |

## How to use

An independent implementation should be able to:
1. Reproduce the wallet derivation (entropy → mnemonic → BIP39 seed → fingerprint).
2. Decode the Vault Key from its text representation (`CVK1.` prefix).
3. Derive the capsule key using HKDF-SHA256 (salt=capsuleId, info=CLOAKVAULT-V1-CAPSULE-KEY||generation).
4. Decrypt the capsule using XChaCha20-Poly1305 and recover the 32-byte entropy.
5. Verify RS encoding: RS-encode the capsule bytes and compare to the stored codeword.
6. Rejoin the two shares to recover the Vault Key.

## Construction

- Deterministic RNG: SHA-256(seed32 || uint64_be(counter)), seed = SHA-256("test:" || uint64_be(n)).
- All values from DeterministicTestRNG(seed=1) except shares (seed=2).
