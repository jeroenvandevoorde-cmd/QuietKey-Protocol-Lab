"""
CloakVault v3 interop acceptance tests (Python side).

Sources of truth: docs/cloakvault-protocol-v3.md and
docs/cloakvault-v3-test-vector.json ONLY. The published vector values are
the proof: the code below reproduces bytes it was never handed as answers.
"""

import json
import pathlib

import pytest

import cloakvault_v3 as cv

ROOT = pathlib.Path(__file__).resolve().parents[2]
VECTOR = json.loads((ROOT / "docs" / "cloakvault-v3-test-vector.json").read_text())


# ── Criterion 3: RFC 8452 Appendix C.2 KATs via pyca/cryptography ────────────
KEY = bytes.fromhex("0100000000000000000000000000000000000000000000000000000000000000")
NONCE = bytes.fromhex("030000000000000000000000")

C2_VECTORS = [
    ("", "", "07f5f4169bbf55a8400cd47ea6fd400f"),
    ("01000000000000000000000000000000", "",
     "85a01b63025ba19b7fd3ddfc033b3e76c9eac6fa700942702e90862383c6c366"),
    ("0100000000000000000000000000000002000000000000000000000000000000", "",
     "4a6a9db4c8c6549201b9edb53006cba821ec9cf850948a7c86c68ac7539d027fe819e63abcd020b006a976397632eb5d"),
    ("0200000000000000", "01",
     "1de22967237a813291213f267e3b452f02d01ae33e4ec854"),
]


@pytest.mark.parametrize("pt,aad,expected", C2_VECTORS)
def test_rfc8452_c2_kats(pt, aad, expected):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCMSIV

    sealed = AESGCMSIV(KEY).encrypt(NONCE, bytes.fromhex(pt), bytes.fromhex(aad) or None)
    assert sealed.hex() == expected
    opened = AESGCMSIV(KEY).decrypt(NONCE, bytes.fromhex(expected), bytes.fromhex(aad) or None)
    assert opened.hex() == pt


# ── Criterion 1: decode the published vector from footer lines only ──────────
def test_decode_published_vector():
    footer_text = "\n".join(VECTOR["rendering"]["footerLines"])
    vault_key = bytes.fromhex(VECTOR["inputs"]["vaultKeyHex"])

    result = cv.decode_token(footer_text)
    assert result["extracted"] is True
    assert result["checksum_valid"] is True
    assert result["capsule"].hex() == VECTOR["capsule"]["capsuleHex"]

    entropy = cv.decode_pipeline(footer_text, vault_key)
    assert entropy.hex() == VECTOR["inputs"]["seedEntropyHex"]

    fingerprint = cv.master_fingerprint(VECTOR["inputs"]["mnemonic"])
    assert fingerprint == VECTOR["expectedRecovery"]["fingerprint"] == "3E1F-3AE0"


# ── Criterion 2: encode to the published vector, byte-for-byte ────────────────
def test_encode_published_vector():
    entropy = bytes.fromhex(VECTOR["inputs"]["seedEntropyHex"])
    vault_key = bytes.fromhex(VECTOR["inputs"]["vaultKeyHex"])

    derived = cv.derive_capsule_key(vault_key)
    assert derived.hex() == VECTOR["hkdf"]["derivedCapsuleKeyHex"]

    capsule = cv.create_capsule(entropy, vault_key)
    assert capsule.hex() == VECTOR["capsule"]["capsuleHex"]

    codeword = cv.rs_encode(capsule)
    assert codeword[49:].hex() == VECTOR["reedSolomon"]["parityHex"]

    token = cv.encode_pipeline(entropy, vault_key)
    assert token == VECTOR["bech32"]["token"]
    assert len(token) == 142

    lines = cv.render_footer_lines(token, "12/08/2026")
    assert lines == VECTOR["rendering"]["footerLines"]

    # Deterministic-equality property (spec §2.3): byte-identical re-creation.
    assert cv.create_capsule(entropy, vault_key) == capsule


# ── Criterion 4: erasure behavior per spec §3.3–§3.4 ─────────────────────────
def test_burst_erasure_within_budget_decodes():
    token = VECTOR["bech32"]["token"]
    body = list(token[3:])
    # Coffee-stain: contiguous run of 40 marked characters (well within the
    # 34-byte erasure budget: 40 chars * 5 bits span ≤ 26 bytes).
    for i in range(20, 60):
        body[i] = "?"
    result = cv.decode_token("cv0" + "".join(body))
    assert result["checksum_valid"] is None  # unverifiable with erasure marks
    assert result["capsule"] is not None
    assert result["capsule"].hex() == VECTOR["capsule"]["capsuleHex"]
    assert result["erasures"] <= 34


def test_erasures_beyond_budget_fail_cleanly():
    token = VECTOR["bech32"]["token"]
    body = list(token[3:])
    for i in range(0, 70):  # spans > 34 codeword bytes
        body[i] = "?"
    result = cv.decode_token("cv0" + "".join(body))
    assert result["capsule"] is None
    assert result["failure"] is not None  # clean typed failure, no output


def test_mark_as_erasure_beats_guessing():
    """Spec §3.4: marking degraded chars costs 1 parity byte; guessing costs 2."""
    token = VECTOR["bech32"]["token"]
    # 50 chars marked as erasures (≈32 bytes): decodes.
    marked = list(token[3:])
    for i in range(30, 80):
        marked[i] = "?"
    assert cv.decode_token("cv0" + "".join(marked))["capsule"] is not None
    # The same 50 chars silently wrong (>17 error bytes): must fail.
    guessed = list(token[3:])
    for i in range(30, 80):
        guessed[i] = cv.CHARSET[(cv.CHARSET.index(guessed[i]) + 1) % 32]
    assert cv.decode_token("cv0" + "".join(guessed))["capsule"] is None


# ── Structural extraction / genre-independence (spec §4.4) ───────────────────
def test_genre_independent_extraction():
    token = VECTOR["bech32"]["token"]
    wrapped = "\n".join(token[i : i + 48] for i in range(0, len(token), 48))
    for fake in [
        f"https://tabsandchords.example.net/song/4321?id={wrapped}&v=1",
        f"travel notes, day 12\nhttps://blog.example.org/entry?id={wrapped}",
    ]:
        result = cv.decode_token(fake)
        assert result["capsule"].hex() == VECTOR["capsule"]["capsuleHex"]


def test_sentinel_destroyed_length_run_fallback():
    token = VECTOR["bech32"]["token"]
    damaged = "???" + token[3:]
    assert cv.extract_token(f"x_id={damaged}") is not None


# ── Round-trip sanity independent of the vector ──────────────────────────────
def test_fresh_round_trip():
    entropy = bytes(range(32))[::-1]
    vault_key = bytes([0xAA] * 32)
    token = cv.encode_pipeline(entropy, vault_key)
    assert cv.decode_pipeline(token, vault_key) == entropy
    with pytest.raises(cv.CapsuleError):
        cv.decode_pipeline(token, bytes([0xAB] * 32))  # wrong key: clean failure
