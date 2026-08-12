---
name: CloakVault process rules
description: Durable process rules and frozen protocol decisions for CloakVault work.
---

# CloakVault — durable process rules & decisions

## Process rules (owner-binding)
- Work is milestone-gated: after each milestone, report results and STOP for explicit owner approval. Never build ahead of an approved gate.
- KAT hard stop: only authoritative published test vectors, copied verbatim; never generate, substitute, or adjust an expected value. A failing KAT means fix the implementation.
- Ambiguity rule: surface any cryptographic-design ambiguity to the owner instead of choosing silently.
- No backend/storage/telemetry; only tesseract.js may fetch. Never log or persist secrets. Permanent TEST USE ONLY banner.

## Frozen v3 protocol decisions (owner-approved; do not change)
- v1 slot-cloak grammar architecture was abandoned after plausibility measurements failed the human gate (`reports/measurement-*` kept as decision records). v3 puts the payload in an opaque Bech32 footer token styled as print exhaust; the page body is a real recipe with zero payload.
- Capsule v2: AES-256-GCM-SIV, HKDF-SHA256 (empty salt, info "CLOAKVAULT-V3-CAPSULE-KEY"), AAD = version byte, fixed all-zero nonce — deterministic output is INTENDED (equivalent-card redundancy); do not "fix" with randomness.
- Footer codec: RS(83,49) parity 34, GF(2⁸) 0x11D, roots α⁰…α³³; Bech32 charset, HRP "cv" checksum-only, sentinel `cv0`, 142-char token. Readers MUST mark degraded chars as erasures, never guess (spec §3.4 is normative).
- The spec (`docs/cloakvault-protocol-v3.md`) and test vector are FROZEN; independent Python interop (written from spec alone) matched byte-for-byte. Any protocol edit invalidates the interop guarantee and needs an owner gate.
- CI validations `test`, `interop-python`, `interop-cross` guard spec/TS/Python drift — keep all three green before any merge.

## Backlog (owner-sequenced, not yet tasks)
- Multi-genre cover templates: content-only workstream; the footer codec is genre-independent, no protocol change allowed.
- Signing capability: strictly AFTER a hardware-validated recovery device exists.
