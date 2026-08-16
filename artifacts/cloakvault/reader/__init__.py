"""QuietKey Gate A Reader v0.2 — DEVELOPMENT reader (NOT GATE-A1 / NOT PRODUCTION).

This package is the Reader v0.2 hardening work layer:
capture-quality gating, structural footer location, locally deformable
line registration, structural token extraction, and calibration/validation
separation. It never touches the frozen v3 protocol (spec, vector, RS,
Bech32, AEAD) — protocol decoding is delegated to the frozen reference
decoder `interop/python/cloakvault_v3.py`.

Distinct from:
  * the historical spike reader (spike/reader/, preserved as-run evidence);
  * any future production terminal reader (separate optics calibration).
"""
READER_VERSION = "0.2-dev"
