/**
 * Self-Test shell page (CloakVault v3, footer codec).
 *
 * The full in-browser Self-Test assembly (auto-run KATs + vector export)
 * is a later milestone. The complete suite currently runs in the project's
 * automated test runner; this page documents exactly what it covers.
 */
export default function SelfTestPage() {
  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <h1 className="text-xl font-semibold" data-testid="text-selftest-title">Self-Test</h1>

      <div className="border rounded p-4 space-y-2">
        <p className="text-sm text-gray-700">
          The in-browser self-test page (auto-run known-answer tests and
          deterministic vector export) is assembled in a later milestone. The
          complete suite currently runs in the project&rsquo;s automated test
          runner and covers:
        </p>
        <ul className="text-sm list-disc pl-5 space-y-1 text-gray-700">
          <li>External KATs: BIP39 (Trezor vectors incl. all-zero entropy), BIP32 test
            vector 1, RFC 5869 HKDF cases 1–2, XChaCha20-Poly1305, and RFC 8452
            AES-256-GCM-SIV (Appendix C.2, four vectors).</li>
          <li>Capsule v1 (93-byte) and v2 (49-byte) round-trip, determinism, and
            tamper-failure tests.</li>
          <li>Reed–Solomon GF(2^8) error and erasure boundary suite.</li>
          <li>Footer codec: 1000-capsule round-trip, exhaustive single-character
            checksum detection, erasure-limit and burst/scatter damage tests,
            genre-independence, and body/footer independence.</li>
          <li>XOR share round-trip and mismatch tests.</li>
        </ul>
      </div>

      <div className="border rounded p-4 space-y-2">
        <h2 className="font-semibold text-sm">Damage harness</h2>
        <p className="text-sm text-gray-700">
          The six physical-damage models (coffee, scratch, crumple as clean erasures;
          scuff, fade, crease as silent errors) run as a development harness
          (<span className="font-mono">scripts/damage-harness.ts</span>), reporting decode
          success and erasure/error counts per parity setting. Results feed the
          <span className="font-mono"> RS_PARITY_BYTES</span> constant empirically.
        </p>
      </div>
    </div>
  );
}
