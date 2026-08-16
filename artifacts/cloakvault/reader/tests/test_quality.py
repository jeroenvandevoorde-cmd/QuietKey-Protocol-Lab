"""Task 2 — capture-quality gate unit tests (deterministic, synthetic)."""
import numpy as np

from reader.quality import (
    FOOTER_SIGNAL_TOO_WEAK,
    GLARE,
    LOW_SHARPNESS,
    UNDEREXPOSED,
    assess_quality,
)
from reader.synthglyphs import apply_blur, render_page


def make_good_page():
    return render_page(["the quick brown fox 012345 qpzry9x8gf2tvdw0s3jn54khce6mua7l"] * 3)


def test_good_page_accepts(dev_profile):
    q = assess_quality(make_good_page(), dev_profile.quality)
    assert q.status == "ACCEPT", q.reasons
    assert q.metrics["footer_line_candidates"] >= 1


def test_result_is_structured(dev_profile):
    q = assess_quality(make_good_page(), dev_profile.quality)
    assert isinstance(q.reasons, list)
    assert "laplacian_variance" in q.metrics and "footer_periodicity" in q.metrics


def test_blur_rejected_with_reason(dev_profile):
    img = apply_blur(make_good_page(), 9)
    q = assess_quality(img, dev_profile.quality)
    assert q.status == "RECAPTURE"
    assert LOW_SHARPNESS in q.reasons


def test_underexposed_rejected(dev_profile):
    img = make_good_page() * 0.01
    q = assess_quality(img, dev_profile.quality)
    assert q.status == "RECAPTURE"
    assert UNDEREXPOSED in q.reasons


def test_glare_detected(dev_profile):
    img = make_good_page()
    h, w = img.shape
    img[int(h * 0.6) :, int(w * 0.3) : int(w * 0.9)] = 1.0  # large specular patch over footer
    q = assess_quality(img, dev_profile.quality)
    assert q.status == "RECAPTURE"
    assert GLARE in q.reasons or FOOTER_SIGNAL_TOO_WEAK in q.reasons
    assert q.metrics["glare_region_frac"] > dev_profile.quality["glare_max_region_frac"]


def test_blank_page_rejected_for_footer_signal(dev_profile):
    img = np.ones((300, 500))
    q = assess_quality(img, dev_profile.quality)
    assert q.status == "RECAPTURE"
    assert FOOTER_SIGNAL_TOO_WEAK in q.reasons


def test_deterministic(dev_profile):
    img = make_good_page()
    q1 = assess_quality(img, dev_profile.quality)
    q2 = assess_quality(img, dev_profile.quality)
    assert q1.metrics == q2.metrics and q1.reasons == q2.reasons
