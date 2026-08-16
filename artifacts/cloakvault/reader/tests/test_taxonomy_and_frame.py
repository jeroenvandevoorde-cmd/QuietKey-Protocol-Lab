"""Tasks 1b/11/12/13 — result taxonomy, stage diagnostics, frame API."""
import numpy as np

from reader.frame import read_frame
from reader.synthglyphs import apply_blur, render_page
from reader.taxonomy import (
    CATEGORY_STAGE,
    PRE_CLASSIFICATION_CATEGORIES,
    FrameResult,
    ResultCategory,
    Stage,
    StageDiagnostic,
)


def test_all_required_categories_exist():
    for name in [
        "AUTHENTICATED_SUCCESS", "CAPTURE_QUALITY_REJECT", "FOOTER_LOCALIZATION_FAIL",
        "REGISTRATION_FAIL", "RS_BUDGET_EXCEEDED", "AUTHENTICATION_FAIL", "INTERNAL_ERROR",
    ]:
        assert ResultCategory(name)


def test_no_generic_fail_category():
    assert "FAIL" not in [c.value for c in ResultCategory]


def test_all_required_stages_exist():
    for name in ["CAPTURE", "PAGE", "FOOTER", "REGISTRATION", "CLASSIFICATION",
                 "TOKEN_EXTRACTION", "RS", "AEAD"]:
        assert Stage(name)


def test_failure_identifies_stage():
    r = FrameResult(
        ResultCategory.FOOTER_LOCALIZATION_FAIL,
        [StageDiagnostic(Stage.CAPTURE, True),
         StageDiagnostic(Stage.FOOTER, False, "insufficient periodic line candidates")],
    )
    assert r.failing_stage() == Stage.FOOTER
    assert CATEGORY_STAGE[r.category] == Stage.FOOTER


def test_blurred_capture_rejected_before_deep_decode(dev_profile):
    img = apply_blur(render_page(["qpzry9x8gf2tvdw0s3jn54khce6mua7lqpzry9x8gf2tvdw0"] * 3), 9)
    r = read_frame(img, dev_profile)
    assert r.category == ResultCategory.CAPTURE_QUALITY_REJECT
    cap = r.stages[0]
    assert cap.stage == Stage.CAPTURE and not cap.ok and cap.reason
    # pre-classification failure: counts are NOT damage measurements
    assert r.category in PRE_CLASSIFICATION_CATEGORIES
    assert r.classified_chars is None and r.erasure_count is None


def test_one_image_in_one_result_out(dev_profile):
    """Multi-frame READINESS: independent frames give independent results."""
    img = np.ones((300, 500))
    r1 = read_frame(img, dev_profile)
    r2 = read_frame(img, dev_profile)
    assert isinstance(r1, FrameResult) and isinstance(r2, FrameResult)
    assert r1.to_dict() == r2.to_dict()


def test_frame_result_serializable(dev_profile):
    r = read_frame(np.ones((300, 500)), dev_profile)
    d = r.to_dict()
    assert d["category"] in {c.value for c in ResultCategory}
    assert all("stage" in s for s in d["stages"])


def test_no_token_content_in_diagnostics(dev_profile, test_token):
    """Diagnostics must never leak token/secret contents."""
    import json

    img = render_page(["header text"] + [test_token[i:i+48] for i in range(0, 142, 48)])
    r = read_frame(img, dev_profile)
    blob = json.dumps(r.to_dict())
    assert test_token not in blob
    assert test_token[3:40] not in blob
