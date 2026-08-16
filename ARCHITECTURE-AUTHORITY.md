# Architecture Authority — read before changing anything

## Current system architecture

The current QuietKey system architecture is governed by the **QK2-04 blueprint**, maintained outside this repository.

Its non-negotiable system rules include:

- native 2-of-2 P2WSH wallet;
- leg A originates from the seed encrypted into the Recovery Document capsule;
- leg B belongs to the smart-card secure element;
- normal QuietKey recovery/spending requires the **Recovery Document + an authorized smart card**;
- Independent Recovery is mandatory and protects the **64-byte `VaultKey ‖ keyB` payload**;
- no human-memory security dependency and no memorized PIN/passphrase;
- the Recovery Document body carries **zero payload** and is never procedurally generated from secret material;
- reader conformance follows the frozen protocol: uncertain or degraded characters become erasures and are never confidently guessed.

Details that QK2-04 deliberately leaves for later gates — including exact leg-B derivation/profile, card sealing mechanisms, KMAC representation, provisioning/export state-machine details, and the final Independent Recovery serialization — MUST NOT be invented by this repository.

## Current wire protocol

The current document-capsule wire protocol is governed solely by:

- `artifacts/cloakvault/docs/cloakvault-protocol-v3.md`
- `artifacts/cloakvault/docs/cloakvault-v3-test-vector.json`

The wire capsule version byte is `0x02`.

These files are frozen. A reference implementation does not have authority to redefine them. Any future protocol change requires an explicitly approved new version, specification, conformance material, and independent interoperability work.

## Current reference implementations

The v3 TypeScript code under `artifacts/cloakvault/src/` and the independent Python implementation under `artifacts/cloakvault/interop/python/` implement and test the frozen wire protocol.

They are **reference/test implementations, not architectural or protocol authorities**.

Authority flows from specification to implementation, never from implementation back into the specification.

## Historical material

The following are superseded historical designs and MUST NOT be treated as current architecture:

- v1 93-byte XChaCha20-Poly1305 capsule;
- v1 RS(121,93), 28-parity/interleaving profile;
- v1 32-byte Vault-Key-only Independent Recovery share format;
- abandoned slot-cloak / payload-in-body designs.

Historical material may remain for compatibility, evidence, or regression testing only when unmistakably labeled **LEGACY / SUPERSEDED**.

## Browser Protocol Laboratory

The current web application is a **Browser Protocol Laboratory**.

It exists to exercise, inspect, test, and demonstrate the document-capsule wire protocol.

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
