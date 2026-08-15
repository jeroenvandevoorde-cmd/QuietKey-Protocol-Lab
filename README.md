# QuietKey

QuietKey (protocol/codebase name **CloakVault**, retained as a frozen
historical label) is an air-gapped Bitcoin seed-backup and recovery system.
The encrypted seed capsule lives in the footer token of an ordinary-looking
printed document; recovery requires the printed document **plus** a separate
256-bit Vault Key. This repository is the reference implementation.

## Status

> **EXPERIMENTAL — TEST USE ONLY — NOT FOR REAL FUNDS.**
> Gates A–C (capture spike, card applet, external audit) are not complete.

## Authority map

- The **protocol** is governed by
  [`artifacts/cloakvault/docs/cloakvault-protocol-v3.md`](artifacts/cloakvault/docs/cloakvault-protocol-v3.md)
  together with the frozen conformance vector
  [`artifacts/cloakvault/docs/cloakvault-v3-test-vector.json`](artifacts/cloakvault/docs/cloakvault-v3-test-vector.json)
  (wire version byte `0x02`).
- The **system/device design** is governed by the QK2-03 blueprint, maintained
  outside this repository.
- This repository is the **reference implementation**. Documents cite the
  spec; they never copy it.

## Repository layout

- `artifacts/cloakvault` — the product: web app, protocol spec, frozen test
  vector, Python interop suite, and capture-spike materials (`spike/`).
- `artifacts/protocol-test-vectors` — frozen v1 vectors (historical, still
  decodable under their own rules).
- `artifacts/cloakvault/reports` — measurement reports, preserved as history.
- Other workspace artifacts (`artifacts/api-server`, `artifacts/mockup-sandbox`)
  and `lib/*` are Replit monorepo scaffolding, not part of the product.

## How to verify

All three validations, in full (none may be reduced or sampled):

```sh
# 1. TypeScript: typecheck + full 97-test vitest suite
pnpm install --frozen-lockfile
pnpm --filter @workspace/cloakvault run typecheck
pnpm --filter @workspace/cloakvault run test

# 2. Python interop suite (12 tests; requires Python 3.12+, cryptography, pytest)
pytest artifacts/cloakvault/interop/python -q

# 3. Cross-implementation check (TS ⇄ Python)
pnpm --filter @workspace/cloakvault run interop:cross
```

An independent implementation can be built from the specification alone and
checked against the worked conformance vector (entropy → token → master
fingerprint `3E1F-3AE0`).

## License

MIT — see [LICENSE](LICENSE). The license covers all repository contents,
including the protocol specification.
