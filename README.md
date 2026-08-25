# QuietKey

QuietKey (protocol/codebase name **CloakVault**, retained as a frozen
historical label) is an air-gapped Bitcoin cold-storage system.  Its current
product architecture is intentionally not restated by this evidence bench.

This repository is the **physical-evidence bench** for capture-corpus custody
and reader research under QuietKey QK-DEC-085.  Its current authority pin is
QuietKey commit `ae697d1f88eb4deaa8adb9ac999db7d445550f7d` (QK-DEC-104 for
Reader v0.2).  No source migrates between this bench and QuietKey while OD-08
remains open.

The Browser Protocol Laboratory and its v3 implementation remain preserved
old-format reference material.  They must not be interpreted as current
QuietKey product code or as the production secret-handling model.

**Read [`ARCHITECTURE-AUTHORITY.md`](ARCHITECTURE-AUTHORITY.md) before
changing anything — it defines what governs what.**

> ## ⚠ EXPERIMENTAL — TEST USE ONLY — NOT FOR REAL FUNDS
>
> This bench does not establish any product Gate result.
> Every published value in this repository uses deliberately public test
> secrets. Do not protect real funds with any part of this system.

## Authority map

- **Current architecture and product protocol** are governed outside this
  repository by the Owner-controlled QuietKey source and Decision Log.
- **Preserved old-format protocol material** is governed only within its own
  historical scope by
  [`artifacts/cloakvault/docs/cloakvault-protocol-v3.md`](artifacts/cloakvault/docs/cloakvault-protocol-v3.md)
  together with the frozen conformance vector
  [`artifacts/cloakvault/docs/cloakvault-v3-test-vector.json`](artifacts/cloakvault/docs/cloakvault-v3-test-vector.json)
  (capsule version byte `0x02`).
- **Reader v0.2** is isolated bench research that emits symbols and explicit
  erasures only.  It contains no QuietKey codec, RS, or AEAD implementation and
  cannot read fresh M19-R anchors before later Owner authorization.
- **Legacy implementations** never override current QuietKey authority.

## Repository layout

- `artifacts/cloakvault` — preserved Browser Protocol Laboratory material,
  capture evidence, and reader research; it is not the product implementation.
- `artifacts/cloakvault/reader` — LEGACY / OLD-FORMAT reader research.
- `artifacts/cloakvault/qka1_reader_v02` — isolated current Reader v0.2 bench
  package.
- `artifacts/protocol-test-vectors` — frozen v1 vectors (historical, still
  decodable under their own frozen rules).
- `artifacts/cloakvault/reports` — measurement reports, preserved history.
- Other workspace artifacts (`artifacts/api-server`,
  `artifacts/mockup-sandbox`) and `lib/*` are monorepo scaffolding, not part
  of the product.

## How to verify

The isolated QKA1 Reader v0.2 scaffold is dependency-free:

```sh
python3 -m unittest discover \
  -s artifacts/cloakvault/qka1_reader_v02/tests \
  -t artifacts/cloakvault -v
```

The commands below validate only the preserved old-format Browser Protocol
Laboratory.  They do not validate Reader v0.2 or current QuietKey product code.

```sh
# Old-format TypeScript suite
pnpm install --frozen-lockfile
pnpm --filter @workspace/cloakvault run typecheck
pnpm --filter @workspace/cloakvault run test

# Old-format Python interop suite (requires Python 3.12, cryptography, pytest)
pip install cryptography pytest
pytest artifacts/cloakvault/interop/python

# Old-format cross-implementation check (TS ⇄ Python) — the script invokes
#    interop/python/.venv/bin/python, so create that virtualenv first:
python3 -m venv artifacts/cloakvault/interop/python/.venv
artifacts/cloakvault/interop/python/.venv/bin/pip install cryptography
pnpm --filter @workspace/cloakvault run interop:cross
```

An implementation of the preserved old-format protocol can be checked against
its worked conformance vector (entropy → token → master fingerprint
`3E1F-3AE0`).

## License

MIT — see [`LICENSE`](LICENSE). The license covers all repository contents,
including the protocol specification.
