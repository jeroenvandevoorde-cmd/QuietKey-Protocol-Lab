# QKA1 Reader v0.2

This package is isolated bench-only reader research under QuietKey
QK-DEC-085 and QK-DEC-104, pinned at QuietKey commit
`ae697d1f88eb4deaa8adb9ac999db7d445550f7d`.

This package defines the fail-closed boundary between an image-facing reader
and a separately authored codec-and-authentication adapter. It binds an exact
in-memory frame member, byte count, and SHA-256 to the profile-bound corpus
manifest before decoding any pixels. A deterministic standard-library PNG
path then locates the page's four edges, projectively rectifies its fixed
footer grid, infers the 116-, 122-, or 128-position profile from the printed
second-line boundary, and classifies each cell against a profile-bound
template model. The caller cannot supply a profile. Ambiguous profile geometry
requests recapture, and the result never reports an authenticated outcome.

The concrete engineering fixture in `fixtures/substance-v1.json` freezes the
geometry, thresholds, two clean-render training sources, three deterministic
synthetic transforms, and all three profile clean-render holdouts. Its status
is development-only, not for scoring, and not a product default. The tests
build the synthetic partition and model from those exact bytes, verify every
artifact hash, recover all three held-out clean-render transcripts, and
projectively rectify a 1.5-times oversampled, rotated, non-rectangular full-page
synthetic frame without caller-supplied crop or profile data. Oversampling
keeps the fixture focused on geometry instead of introducing a second lossy
rasterization; it recovers the exact transcript under unchanged thresholds.
The profile binds an exact manifest of implementation-file hashes and labels
that implementation `PENDING_BEFORE_SCORING`; it does not misidentify the
frozen-render source commit as the reader's own commit. A commit freeze of the
implementation, model, geometry, and partition remains required before any
future scored holdout run. These clean-render assertions are engineering
regression checks, not a scored comparison.

The package deliberately contains:

- no third-party image or OCR dependency;
- no imports from the old-format `reader` or `interop` packages;
- no Reed-Solomon, base32 packing, capsule, or AEAD implementation;
- no default profile, model, threshold, or production configuration;
- no filesystem corpus loader or camera path; and
- no permission to process fresh M19-R anchors or their real holdouts.

The image transport is deliberately narrow: bounded, non-interlaced, 8-bit
PNG only. The locator consumes pixels and its exact hashed geometry artifact;
it accepts no decoy text, rig-fiducial or scale-bar coordinates, profile label,
manual crop, or candidate list. The classifier returns one hypothesis per fixed cell;
the frozen confidence and margin thresholds convert uncertainty to an erasure,
with no aliases or normalization.

The only reader-authorized corpus purposes are frozen clean renders and a
preregistered synthetic training partition.  Old spike/Bridge material is
morphology-reference-only.  Fresh anchors remain rejected in code until a
later Owner-ratified row changes that policy.

Run the dependency-free scaffold tests from the repository root:

```sh
python3 -m unittest discover \
  -s artifacts/cloakvault/qka1_reader_v02/tests \
  -t artifacts/cloakvault -v
```
