/**
 * Self-Test page — runs the ported vitest suites in the browser.
 *
 * - On load: auto-runs the SMOKE subset (all fast tests, full counts).
 * - "Run Full Suite": runs every test unreduced (1000 = 1000, exhaustive =
 *   exhaustive) in the browser.
 * - "Export Test Vector": regenerates the frozen conformance vector from the
 *   running build and offers it for download ONLY if it byte-matches
 *   docs/cloakvault-v3-test-vector.json.
 */
import { useEffect, useRef, useState } from 'react';
import { SUITE_GROUPS, suiteCounts } from '@/lib/selftest/suites';
import { runGroups, type GroupResult, type TestScope } from '@/lib/selftest/runner';
import { checkVectorByteMatch, type VectorCheck } from '@/lib/selftest/vector';

const COUNTS = suiteCounts();

function StatusBadge({ g }: { g: GroupResult }) {
  if (!g.done && g.tests.length === 0)
    return <span className="text-xs text-neutral-400">queued…</span>;
  if (!g.done) return <span className="text-xs text-amber-600">running…</span>;
  return g.failed === 0 ? (
    <span className="text-xs font-semibold text-emerald-700">PASS</span>
  ) : (
    <span className="text-xs font-semibold text-red-700">FAIL</span>
  );
}

function GroupCard({ g }: { g: GroupResult }) {
  const [open, setOpen] = useState(false);
  const total = COUNTS[g.id];
  return (
    <div className="rounded-lg border border-neutral-200 bg-white" data-testid={`group-${g.id}`}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
        data-testid={`button-toggle-${g.id}`}
      >
        <div>
          <div className="text-sm font-medium text-neutral-900">{g.label}</div>
          <div className="mt-0.5 text-xs text-neutral-500">
            {g.passed} passed{g.failed > 0 ? `, ${g.failed} failed` : ''} ·{' '}
            {g.tests.length}/{g.scope === 'full' ? total.full : total.smoke} run ·{' '}
            {g.ms.toFixed(0)} ms
          </div>
        </div>
        <StatusBadge g={g} />
      </button>
      {open && (
        <ul className="border-t border-neutral-100 px-4 py-2">
          {g.tests.map((t) => (
            <li key={t.name} className="flex items-start gap-2 py-1 text-xs">
              <span className={t.ok ? 'text-emerald-600' : 'text-red-600'}>
                {t.ok ? '✓' : '✗'}
              </span>
              <span className="flex-1 text-neutral-700">
                {t.name}
                {!t.ok && t.error && (
                  <span className="mt-0.5 block font-mono text-red-700">{t.error}</span>
                )}
              </span>
              <span className="text-neutral-400">{t.ms.toFixed(1)} ms</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function SelfTestPage() {
  const [results, setResults] = useState<GroupResult[]>([]);
  const [scope, setScope] = useState<TestScope>('smoke');
  const [running, setRunning] = useState(false);
  const [vector, setVector] = useState<VectorCheck | null>(null);
  const [showExportWarning, setShowExportWarning] = useState(false);
  const startedRef = useRef(false);

  const run = async (s: TestScope) => {
    setRunning(true);
    setScope(s);
    try {
      await runGroups(SUITE_GROUPS, s, setResults);
      setVector(checkVectorByteMatch());
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    if (startedRef.current) return;
    startedRef.current = true;
    void run('smoke');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const allDone = results.length > 0 && results.every((g) => g.done);
  const totalPassed = results.reduce((s, g) => s + g.passed, 0);
  const totalFailed = results.reduce((s, g) => s + g.failed, 0);
  const totalRun = totalPassed + totalFailed;
  const fullTotal = Object.values(COUNTS).reduce((s, c) => s + c.full, 0);
  const smokeTotal = Object.values(COUNTS).reduce((s, c) => s + c.smoke, 0);

  const exportVector = () => {
    if (!vector || !vector.byteMatch) return;
    const blob = new Blob([vector.regenerated], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'cloakvault-v3-test-vector.json';
    a.click();
    URL.revokeObjectURL(url);
    setShowExportWarning(false);
  };

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <h1 className="text-xl font-semibold text-neutral-900">Self-Test</h1>
      <p className="mt-1 text-sm text-neutral-600">
        Runs the same known-answer tests, boundary suites, and round-trip checks as the
        repository test suite, directly in this browser. The auto-run smoke subset contains
        every fast test at full counts ({smokeTotal} of {fullTotal} tests); the full suite
        adds the long-running tests with nothing reduced — 1000 round-trip payloads means
        1000, and exhaustive checks stay exhaustive.
      </p>

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          disabled={running}
          onClick={() => void run('full')}
          className="rounded-md bg-neutral-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
          data-testid="button-run-full-suite"
        >
          {running && scope === 'full' ? 'Running full suite…' : 'Run Full Suite'}
        </button>
        <button
          type="button"
          disabled={running}
          onClick={() => void run('smoke')}
          className="rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-800 disabled:opacity-50"
          data-testid="button-run-smoke"
        >
          Re-run smoke subset
        </button>
        <button
          type="button"
          disabled={!vector}
          onClick={() => setShowExportWarning(true)}
          className="rounded-md border border-neutral-300 px-4 py-2 text-sm font-medium text-neutral-800 disabled:opacity-50"
          data-testid="button-export-vector"
        >
          Export Test Vector
        </button>
      </div>

      {allDone && (
        <div
          className={`mt-4 rounded-md px-4 py-3 text-sm ${
            totalFailed === 0
              ? 'bg-emerald-50 text-emerald-800'
              : 'bg-red-50 text-red-800'
          }`}
          data-testid="text-summary"
        >
          {scope === 'full' ? 'Full suite' : 'Smoke subset'}: {totalPassed}/{totalRun} passed
          {totalFailed > 0 ? ` — ${totalFailed} FAILED` : ''}.
        </div>
      )}

      <div className="mt-4 space-y-3">
        {results.map((g) => (
          <GroupCard key={g.id} g={g} />
        ))}
      </div>

      {vector && (
        <div
          className={`mt-4 rounded-md border px-4 py-3 text-sm ${
            vector.byteMatch && vector.selfCheckOk
              ? 'border-emerald-200 bg-emerald-50 text-emerald-800'
              : 'border-red-200 bg-red-50 text-red-800'
          }`}
          data-testid="text-vector-check"
        >
          Frozen conformance vector: regenerated from this running build and{' '}
          {vector.byteMatch ? 'byte-matches' : 'DOES NOT byte-match'} the committed
          docs/cloakvault-v3-test-vector.json ({vector.regeneratedLength} vs{' '}
          {vector.frozenLength} bytes)
          {vector.selfCheckOk ? '; decode self-check passed.' : '; decode self-check FAILED.'}
        </div>
      )}

      {showExportWarning && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 px-4">
          <div className="max-w-md rounded-lg bg-white p-5 shadow-xl">
            <h2 className="text-sm font-semibold text-neutral-900">
              Export conformance test vector?
            </h2>
            <p className="mt-2 text-sm text-neutral-600">
              This file contains <strong>test secrets only</strong> — a fixed, published seed
              entropy and Vault Key used for interoperability testing. It is exported ONLY if
              the regenerated output byte-matches the frozen specification vector. Never reuse
              any value from it with real funds.
            </p>
            {!vector?.byteMatch && (
              <p className="mt-2 text-sm font-medium text-red-700">
                Export blocked: the regenerated vector does not byte-match the frozen file.
              </p>
            )}
            <div className="mt-4 flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setShowExportWarning(false)}
                className="rounded-md border border-neutral-300 px-3 py-1.5 text-sm"
                data-testid="button-export-cancel"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!vector?.byteMatch}
                onClick={exportVector}
                className="rounded-md bg-neutral-900 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-50"
                data-testid="button-export-confirm"
              >
                I understand — export
              </button>
            </div>
          </div>
        </div>
      )}

      <p className="mt-6 text-xs text-neutral-500">
        Test logic and expected values are taken unchanged from the repository test files
        (some related checks are grouped into one row for display); no counts were reduced
        and no expected values were altered. Memory cleanup in this app is best-effort
        typed-array zeroing only.
      </p>
    </div>
  );
}
