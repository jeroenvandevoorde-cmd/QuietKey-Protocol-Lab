import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]  # artifacts/cloakvault
sys.path.insert(0, str(ROOT))  # so `reader` package imports


@pytest.fixture(scope="session")
def frozen_vector() -> dict:
    """Frozen v3 test vector — read-only; TEST SECRETS ONLY (published)."""
    return json.loads((ROOT / "docs" / "cloakvault-v3-test-vector.json").read_text())


@pytest.fixture(scope="session")
def test_token(frozen_vector) -> str:
    tok = frozen_vector["bech32"]["token"]
    assert len(tok) == 142 and tok.startswith("cv0")
    return tok


@pytest.fixture(scope="session")
def dev_profile():
    from reader.profile import default_development_profile_path, load_profile

    return load_profile(default_development_profile_path())
