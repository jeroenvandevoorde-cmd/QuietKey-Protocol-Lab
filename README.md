# QuietKey

QuietKey (protocol/codebase name **CloakVault**, retained as a frozen
historical label) is an air-gapped Bitcoin cold-storage system. Under the
current QK2-04 architecture, normal recovery/spending requires the printed
Recovery Document **plus an authorized smart card**. The encrypted seed
capsule lives in the footer token of an ordinary-looking printed document.

This repository currently implements the document-capsule protocol in a
**Browser Protocol Laboratory**; because the smart-card layer is not yet
implemented, the laboratory supplies test Vault-Key material directly.
Laboratory behavior must not be interpreted as the production secret-handling
model.

**Read [`ARCHITECTURE-AUTHORITY.md`](ARCHITECTURE-AUTHORITY.md) before
changing anything — it defines what governs what.**

> ## ⚠ EXPERIMENTAL — TEST USE ONLY — NOT FOR REAL FUNDS
>
> Gates A–C (capture spike, card applet, external audit) are not complete.
> Every published value in this repository uses deliberately public test
> secrets. Do not protect real funds with any part of this system.

## Authority map

- **Protocol** is governed by
  [`artifacts/cloakvault/docs/cloakvault-protocol-v3.md`](artifacts/cloakvault/docs/cloakvault-protocol-v3.md)
  together with the frozen conformance vector
  [`artifacts/cloakvault/docs/cloakvault-v3-test-vector.json`](artifacts/cloakvault/docs/cloakvault-v3-test-vector.json)
  (capsule version byte `0x02`).
- **System and device design** is governed by the QK2-04 blueprint,
  maintained outside this repository. See
  [`ARCHITECTURE-AUTHORITY.md`](ARCHITECTURE-AUTHORITY.md) for the full
  authority hierarchy.
- **This repository is the reference implementation.** Documents cite the
  spec; they never copy it.

## Repository layout

- `artifacts/cloakvault` — the product: the client-side app, the frozen
  protocol spec and test vector (`docs/`), the independent Python
  implementation and interop suite (`interop/python/`), and the
  capture-spike materials (`spike/`).
- `artifacts/protocol-test-vectors` — frozen v1 vectors (historical, still
  decodable under their own frozen rules).
- `artifacts/cloakvault/reports` — measurement reports, preserved history.
- Other workspace artifacts (`artifacts/api-server`,
  `artifacts/mockup-sandbox`) and `lib/*` are monorepo scaffolding, not part
  of the product.

## How to verify

All three validations must pass; none may be reduced or sampled.

```sh
# 1. TypeScript suite (97 tests)
pnpm install --frozen-lockfile
pnpm --filter @workspace/cloakvault run typecheck
pnpm --filter @workspace/cloakvault run test

# 2. Python interop suite (12 tests; requires Python 3.12, cryptography, pytest)
pip install cryptography pytest
pytest artifacts/cloakvault/interop/python

# 3. Cross-implementation check (TS ⇄ Python) — the script invokes
#    interop/python/.venv/bin/python, so create that virtualenv first:
python3 -m venv artifacts/cloakvault/interop/python/.venv
artifacts/cloakvault/interop/python/.venv/bin/pip install cryptography
pnpm --filter @workspace/cloakvault run interop:cross
```

An independent implementation can be built from the specification alone and
checked against the worked conformance vector (entropy → token → master
fingerprint `3E1F-3AE0`).

## License

MIT — see [`LICENSE`](LICENSE). The license covers all repository contents,
including the protocol specification.
