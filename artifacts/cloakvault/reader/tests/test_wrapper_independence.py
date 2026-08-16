"""Task 7 — structural wrapper-independence unit tests.

The identical valid 142-char test token embedded in different wrappers and
different line wrappings must always extract to the same canonical token.
These are deterministic unit tests, not empirical document evidence.
"""
import pytest

from reader.token_extract import extract_token_structural


def wrap(text: str, width: int) -> list[str]:
    return [text[i : i + width] for i in range(0, len(text), width)]


def wrappers(token: str) -> dict[str, list[str]]:
    w48 = wrap(token, 48)
    return {
        "A_current_url": [f"https://arecipeforamaster.com/print?id={w48[0]}"] + w48[1:-1] + [w48[-1] + "&v=1"],
        "B_file_url": [f"file:///Users/example/recipe/{w48[0]}"] + w48[1:],
        "C_short_colon": [f"short:{w48[0]}"] + w48[1:-1] + [w48[-1] + ":footer"],
        "D_long_url": [
            "https://an-extremely-long-and-entirely-different-domain-name.example-of-something.org/deep/path/print?session=abcdef&doc="
            + w48[0]
        ] + w48[1:] + ["&trailing=parameters&x=1"],
        "E_no_url": ["Printed from My Recipe Collection"] + w48 + ["Page 1"],
    }


def wrappings(token: str) -> dict[str, list[str]]:
    return {
        "48_48_46": wrap(token, 48),
        "40": wrap(token, 40),
        "52": wrap(token, 52),
        "uneven": [token[:23], token[23:90], token[90:101], token[101:]],
        "single_line": [token],
    }


def test_all_wrappers_extract_same_token(test_token):
    for name, lines in wrappers(test_token).items():
        r = extract_token_structural(lines)
        assert r.token == test_token, f"wrapper {name} failed ({r.method})"


def test_all_wrappings_extract_same_token(test_token):
    for name, lines in wrappings(test_token).items():
        r = extract_token_structural(lines)
        assert r.token == test_token, f"wrapping {name} failed"


def test_wrapper_and_wrapping_combinations(test_token):
    for wname, base in wrappings(test_token).items():
        lines = ["Some ordinary preceding text about recipes."] + base + ["Page 1 of 1"]
        r = extract_token_structural(lines)
        assert r.token == test_token, f"combination {wname} failed"


def test_erasures_preserved_in_candidate(test_token):
    damaged = test_token[:50] + "??" + test_token[52:]
    r = extract_token_structural(wrap(damaged, 48))
    assert r.token == damaged  # uncertainty stays erasure; never guessed


def test_damaged_sentinel_tolerated_structurally(test_token):
    # sentinel is public framing; erasure-tolerant matching is structural
    damaged = "?" + test_token[1:]
    r = extract_token_structural(["prefix-text " + damaged + " suffix"])
    assert r.token == damaged


def test_no_token_returns_none():
    r = extract_token_structural(["just a recipe for bread", "flour water salt yeast"])
    assert r.token is None and r.method is None


def test_no_wrapper_constants_in_current_locator_sources():
    """The new locator/extractor must not embed wrapper knowledge.

    Comments, docstrings, and string literals are stripped with tokenize;
    only executable code is scanned, so prohibitions in documentation do
    not trip the check while real constants do.
    """
    import io
    import tokenize
    from pathlib import Path

    banned = ["arecipeforamaster", "PREFIX", "TOKEN_SLICE", "87, 48, 50", "= 39"]
    for mod in ["structural_locator.py", "token_extract.py", "registration.py", "frame.py"]:
        src = (Path(__file__).parents[1] / mod).read_text()
        code_tokens = [
            t.string
            for t in tokenize.generate_tokens(io.StringIO(src).readline)
            if t.type not in (tokenize.COMMENT, tokenize.STRING, tokenize.NL, tokenize.NEWLINE)
        ]
        code = " ".join(code_tokens)
        for b in banned:
            assert b not in code, f"{mod} contains wrapper constant {b!r} in executable code"
