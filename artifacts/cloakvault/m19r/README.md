# QuietKey M19-R hardware-free pre-work

Status: **bench research; comparison generation disabled**.

This isolated subtree implements only the hardware-free preparation authorized
by QK-DEC-103:

- deterministic 150 dpi clean-render generation from the frozen QK-DEC-094
  bodies, fonts, renderer, and all 18 public QK-DEC-093 payloads;
- deterministic integer-only synthetic morphology primitives and a complete
  comparison plan;
- exact custody registrations for the 29 spike and 19 Bridge originals; and
- a model-freeze preregistration draft that is not active.

`MODEL-CONTRACT.md` gives the exact class operators, six integer metric
algorithms, per-cell center and aggregation rules, and future activation shape.

The clean-render command performs no OCR, footer recognition, symbol
classification, Reed-Solomon work, capsule authentication, scoring, or model
fitting. The synthetic command can validate and summarize the draft but refuses
comparison-image generation in this build. A later, separately committed
Owner-ratified change must add the fixed-path registration, compile its exact
authority bindings, and add the currently absent writer. No activation artifact
or comparison writer exists here.

Payload provenance names the source repository
`https://github.com/jeroenvandevoorde-cmd/QuietKey`, exact source commit, Git
blob, path, and SHA-256. Synthetic validation uses explicit integer algorithms,
capture 1 as the sole future per-cell anchor center, and the fieldwise middle
order statistic of exactly three synthetic realizations; it performs no
cross-cell pooling.

The 29 spike JPEG originals are committed at bench commit
`ba19eea82255f2434f6292c7939f9273d218184a`. The 19 Bridge JPEG originals
remain outside Git in the canonical Replit bench because their capture metadata
is not public; their byte-level custody check is tied to bench HEAD
`60f98eb1633266bf58a36b5eb4a446baeb66974a`. GitHub mirrors commits, not those
19 binary originals. Both sets are old-format morphology references only and
must never be treated as current-token decode, profile, recovery, or Gate
evidence.

Commands, from the repository root:

```text
python3 artifacts/cloakvault/m19r/generate_clean_renders.py
python3 artifacts/cloakvault/m19r/synthetic_model.py validate-draft
python3 artifacts/cloakvault/m19r/synthetic_model.py plan
python3 -m unittest discover -s artifacts/cloakvault/m19r/tests -v
```

`generate-comparison` is intentionally present as a fail-closed command so the
inactive state is machine-tested. Fresh anchors and holdouts are forbidden
inputs in this subtree; physical work remains gated by the separate rig row and
rig readiness.
