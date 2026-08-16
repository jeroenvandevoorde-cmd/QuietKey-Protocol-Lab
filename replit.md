# QuietKey — protocol codebase name: CloakVault

QuietKey is an air-gapped Bitcoin cold-storage system governed by QK2-04. Normal product recovery requires the printed Recovery Document plus an authorized smart card.

This repository currently contains a **Browser Protocol Laboratory** implementing and testing the document-capsule wire protocol. In this laboratory, test Vault-Key material may be supplied directly because the smart-card layer does not yet exist.

The laboratory is **not a model of production QuietKey secret handling**.

**EXPERIMENTAL — TEST USE ONLY — DO NOT USE WITH REAL FUNDS.**

## Read this first

Before making changes, read:

`ARCHITECTURE-AUTHORITY.md`

QK2-04 governs system architecture.

The frozen wire protocol is governed by:

- `artifacts/cloakvault/docs/cloakvault-protocol-v3.md`
- `artifacts/cloakvault/docs/cloakvault-v3-test-vector.json`

Reference implementations never override the specification.

## Product artifact

Current relevant work lives primarily in `artifacts/cloakvault`:

- Browser Protocol Laboratory
- frozen v3 protocol specification
- frozen v3 conformance vector
- TypeScript reference implementation
- independent Python interoperability implementation
- Gate-A/spike materials

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

- client-side protocol laboratory only;
- no persistent secret storage;
- no runtime network dependency;
- never log seeds, Vault Keys, shares, or payload tokens;
- frozen protocol constants are never edited to make tests pass;
- frozen expected values are inputs to validation, not outputs chosen by the implementation;
- test counts are never reduced or sampled;
- uncertain reader characters become erasures, never guesses;
- unresolved QK2-04 Gate-B decisions must be surfaced, never silently chosen;
- no new features are built ahead of an approved milestone.
