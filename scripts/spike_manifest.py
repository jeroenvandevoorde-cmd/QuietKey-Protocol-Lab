#!/usr/bin/env python3
"""Compute SHA-256 for every file under artifacts/cloakvault/spike/ and write
artifacts/cloakvault/spike/MANIFEST.sha256, one line per file:
"<hash>  <relative path>", sorted by path. The manifest file itself is excluded.
"""
import hashlib
from pathlib import Path

SPIKE_DIR = Path(__file__).resolve().parent.parent / "artifacts" / "cloakvault" / "spike"
MANIFEST = SPIKE_DIR / "MANIFEST.sha256"


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    files = sorted(
        p for p in SPIKE_DIR.rglob("*")
        if p.is_file() and p != MANIFEST
    )
    lines = [f"{sha256_of(p)}  {p.relative_to(SPIKE_DIR).as_posix()}" for p in files]
    MANIFEST.write_text("\n".join(lines) + "\n")
    print(MANIFEST.read_text(), end="")


if __name__ == "__main__":
    main()
