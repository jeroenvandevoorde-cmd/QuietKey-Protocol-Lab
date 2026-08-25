# QuietKey — protocol codebase name: CloakVault

QuietKey is an air-gapped Bitcoin cold-storage system governed by the
Owner-controlled QuietKey repository.  This bench is pinned to QuietKey commit
`ae697d1f88eb4deaa8adb9ac999db7d445550f7d`, QK-DEC-085 and QK-DEC-104.

This repository is solely the physical-evidence bench for capture-corpus
custody and reader research.  No source moves between it and QuietKey while
OD-08 remains open.  The Browser Protocol Laboratory is preserved old-format
reference material, not current product code.

The laboratory is **not a model of production QuietKey secret handling**.

**EXPERIMENTAL — TEST USE ONLY — DO NOT USE WITH REAL FUNDS.**

## Read this first

Before making changes, read:

`ARCHITECTURE-AUTHORITY.md`

The Owner-controlled QuietKey repository and its Decision Log govern current
system architecture; this bench does not restate them.

The preserved old-format wire protocol is governed within its historical scope
by:

- `artifacts/cloakvault/docs/cloakvault-protocol-v3.md`
- `artifacts/cloakvault/docs/cloakvault-v3-test-vector.json`

Reference implementations never override the specification.

## Bench scope

Current relevant work lives primarily in `artifacts/cloakvault`:

- physical capture-corpus custody;
- isolated Reader v0.2 research;
- preserved old-format Browser Protocol Laboratory material;
- spike and bridge morphology references.

`artifacts/cloakvault/reader/` is LEGACY / OLD-FORMAT reader research.  Current
Reader v0.2 must not import it, its Bech32/`cv0`/142-symbol constants, or its
old-format codec and authentication path.  Fresh M19-R anchors are unavailable
to all reader execution until a later Owner-ratified scoring row.

There is no product database, product API server, cloud recovery service, telemetry service, or required runtime Internet service.

Other workspace artifacts and `lib/*` are unrelated scaffolding. Never migrate them into QuietKey merely because they exist in the workspace.

## Run and verify

- `pnpm --filter @workspace/cloakvault run dev` — Browser Protocol Laboratory
- `pnpm --filter @workspace/cloakvault run typecheck`
- `pnpm --filter @workspace/cloakvault run test` — complete TypeScript suite, never a subset for acceptance
- `pytest artifacts/cloakvault/interop/python` — independent Python interoperability suite
- `pnpm --filter @workspace/cloakvault run interop:cross` — TS ⇄ Python cross-implementation check

The Python checks require the documented Python environment/dependencies.

## Standing rules

- physical-evidence and reader-research bench only;
- no persistent secret storage;
- no runtime network dependency;
- never log seeds, Vault Keys, shares, or payload tokens;
- frozen protocol constants are never edited to make tests pass;
- frozen expected values are inputs to validation, not outputs chosen by the implementation;
- test counts are never reduced or sampled;
- uncertain reader characters become erasures, never guesses;
- unresolved QuietKey decisions must be surfaced, never silently chosen;
- no new features are built ahead of an approved milestone.
