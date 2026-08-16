"""End-to-end synthetic frame test: token page → authenticated recovery.

Renders the frozen test vector's token (TEST SECRETS ONLY, published) as a
synthetic footer page, runs the full Reader v0.2 pipeline, and verifies an
authenticated decode against the vector's vault key via the frozen
reference decoder. Synthetic engineering test — not Gate A evidence.
"""
import numpy as np

from reader.frame import _frozen_decoder, read_frame
from reader.synthglyphs import render_page
from reader.taxonomy import ResultCategory, Stage


def page_lines(token):
    w48 = [token[i : i + 48] for i in range(0, len(token), 48)]
    return ["Printed from My Recipe Collection"] + w48 + ["Page 1 of 1"]


def test_synthetic_token_page_authenticated_success(frozen_vector, test_token, dev_profile):
    cv = _frozen_decoder()
    vault_key = bytes.fromhex(frozen_vector["inputs"]["vaultKeyHex"])
    expected_seed = bytes.fromhex(frozen_vector["inputs"]["seedEntropyHex"])

    recovered = {}

    def decode_payload(token_text: str) -> dict:
        payload = cv.decode_pipeline(token_text, vault_key)
        recovered["seed"] = payload
        return {"ok": True}

    img = render_page(page_lines(test_token))
    r = read_frame(img, dev_profile, decode_payload=decode_payload)
    assert r.category == ResultCategory.AUTHENTICATED_SUCCESS, r.to_dict()
    assert recovered["seed"] == expected_seed
    assert all(s.ok for s in r.stages)
    assert [s.stage for s in r.stages][-1] == Stage.AEAD


def test_wrong_key_is_authentication_fail(frozen_vector, test_token, dev_profile):
    cv = _frozen_decoder()

    def decode_payload(token_text: str) -> dict:
        cv.decode_pipeline(token_text, b"\x00" * 32)  # wrong vault key
        return {"ok": True}

    img = render_page(page_lines(test_token))
    r = read_frame(img, dev_profile, decode_payload=decode_payload)
    assert r.category == ResultCategory.AUTHENTICATION_FAIL
    assert r.failing_stage() == Stage.AEAD


def test_blank_page_is_explicit_capture_or_footer_fail(dev_profile):
    r = read_frame(np.full((400, 600), 0.88), dev_profile)
    assert r.category in (
        ResultCategory.CAPTURE_QUALITY_REJECT,
        ResultCategory.FOOTER_LOCALIZATION_FAIL,
    )
    assert r.failing_stage() in (Stage.CAPTURE, Stage.FOOTER)


def test_no_key_hook_is_never_reported_as_success(test_token, dev_profile):
    """Status integrity: RS-valid but unauthenticated must NOT be a success."""
    img = render_page(page_lines(test_token))
    r = read_frame(img, dev_profile)  # no decode_payload hook
    assert r.category == ResultCategory.RS_VALID_UNAUTHENTICATED
    assert r.category != ResultCategory.AUTHENTICATED_SUCCESS
    assert r.failing_stage() == Stage.AEAD
    aead = [s for s in r.stages if s.stage == Stage.AEAD][0]
    assert aead.ok is False and aead.reason == "AEAD_NOT_ATTEMPTED"
