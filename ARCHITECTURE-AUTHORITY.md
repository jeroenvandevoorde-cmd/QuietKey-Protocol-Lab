# Architecture Authority — read before changing anything

## Current authority and repository boundary

The current QuietKey system architecture is governed by the Owner-controlled
QuietKey repository.  The bench boundary used here is pinned to QuietKey commit
`ae697d1f88eb4deaa8adb9ac999db7d445550f7d`, especially QK-DEC-085 and
QK-DEC-104.

QuietKey-Protocol-Lab is solely a physical-evidence bench.  It is writable for
capture-corpus custody and reader research under the governing evidence and
provenance rules.  While OD-08 remains open, source code does not migrate from
QuietKey into this repository or from this repository into QuietKey.  A value,
algorithm, or implementation present here has no product authority merely
because it is executable.

Reader v0.2 is bench-only research.  It may consume frozen clean renders and a
preregistered synthetic training partition.  It may not execute against fresh
M19-R anchors until the later QK-DEC-103 scoring row expressly authorizes the
real holdout captures.  It emits fixed-position symbols and explicit erasures
for a separately authored codec-and-authentication adapter; it does not import
or implement the QuietKey codec, Reed-Solomon decoder, or capsule AEAD.

This bench does not restate the current product architecture.  In particular,
it must not infer product behavior from the older QK2-04 descriptions retained
in Git history.  Uncertain reader characters become erasures and are never
guessed; every other product rule and open decision is read from the pinned
QuietKey authority.

## Frozen old-format protocol material

The following files govern only their preserved old-format Browser Protocol
Laboratory protocol:

- `artifacts/cloakvault/docs/cloakvault-protocol-v3.md`
- `artifacts/cloakvault/docs/cloakvault-v3-test-vector.json`

The wire capsule version byte is `0x02`.

These files are frozen historical/reference material.  They do not govern the
current QKA1 print alphabet, geometry, codec, capsule, or Reader v0.2.  A
reference implementation does not have authority to redefine any protocol.

## Old-format reference implementations

The v3 TypeScript code under `artifacts/cloakvault/src/` and the Python
implementation under `artifacts/cloakvault/interop/python/` implement and test
the frozen old-format wire protocol.

They are **reference/test implementations, not architectural or protocol authorities**.

Authority flows from specification to implementation, never from implementation back into the specification.

## Historical material

The following are superseded historical designs and MUST NOT be treated as current architecture:

- v1 93-byte XChaCha20-Poly1305 capsule;
- v1 RS(121,93), 28-parity/interleaving profile;
- v1 32-byte Vault-Key-only Independent Recovery share format;
- abandoned slot-cloak / payload-in-body designs.

Historical material may remain for compatibility, evidence, or regression testing only when unmistakably labeled **LEGACY / SUPERSEDED**.

The existing package at `artifacts/cloakvault/reader/` is old-format reader
research: it recognizes the Bech32 alphabet, the `cv0` sentinel, 142-symbol
tokens, and the old RS(83,49) pipeline.  It is not Reader v0.2 under
QK-DEC-104, is not a source for current constants, and must not be imported by
the isolated QKA1 reader package.

## Legacy Browser Protocol Laboratory

The preserved web application is a **legacy Browser Protocol Laboratory**.

It exists to preserve and exercise the old-format document-capsule wire
protocol.  It is not current QuietKey product code.

It is deliberately **not** a model of production QuietKey:

- secret handling;
- entropy architecture;
- smart-card architecture;
- KMAC handling;
- provisioning;
- signing;
- terminal firmware;
- estate recovery UX.

For example, the laboratory may directly accept or display test mnemonic/Vault-Key material because the production card layer does not yet exist. That behavior MUST NOT be copied into the production terminal design.

## Workspace scaffolding

Workspace scaffolding such as `artifacts/api-server`, `artifacts/mockup-sandbox`, `lib/*`, database/ORM packages, and unrelated Replit template infrastructure is not part of QuietKey.

It must never migrate into `artifacts/cloakvault` or future terminal/card software merely because it exists in the monorepo.
