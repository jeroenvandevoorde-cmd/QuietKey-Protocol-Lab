# QKA1 Reader v0.2 scaffold

This package is isolated bench-only reader research under QuietKey
QK-DEC-085 and QK-DEC-104, pinned at QuietKey commit
`ae697d1f88eb4deaa8adb9ac999db7d445550f7d`.

The scaffold defines the fail-closed boundary between an image-facing reader
and a separately authored codec-and-authentication adapter.  It accepts an
exact in-memory frame bytes through injected locator and classifier interfaces,
after binding the member ID, byte count, and SHA-256 to the profile-bound
corpus manifest.  It emits exactly 116, 122, or 128 fixed-position
symbols/erasures and never reports an authenticated result.

The package deliberately contains:

- no image library or concrete OCR implementation;
- no imports from the old-format `reader` or `interop` packages;
- no Reed-Solomon, base32 packing, capsule, or AEAD implementation;
- no default profile, model, threshold, or production configuration;
- no filesystem corpus loader or camera path; and
- no permission to process fresh M19-R anchors or their real holdouts.

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
