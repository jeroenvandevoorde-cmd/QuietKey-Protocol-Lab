"""Real-print calibration toolkit (Reader v0.2.1, Phase A scaffolding).

Everything here is DEVELOPMENT / NOT GATE-A1. The pipeline is:

  capture JPEGs + CAPTURE-MANIFEST.json + sheet ground truth
    → extract.py   (known-layout labelled glyph windows)
    → evaluate.py  (grouped holdout: leave-one-capture/copy-out)
    → bank.py      (deterministic bank + provenance, Bridge hashes banned)

Phase A ships the code paths and their tests against synthetic renders;
no real calibration captures exist yet (Task 21 checkpoint).
"""
