import { useState } from 'react';
import { SystemRNG } from '@/lib/crypto/rng';
import { FIXED_TEST_MNEMONIC } from '@/lib/crypto/wallet';
import {
  createRecoveryPage,
  CURATED_RECIPES,
  codecParams,
  type CreateResultV3,
} from '@/lib/pipeline';

/** Create page (CloakVault v3, footer codec). */
export default function CreatePage() {
  const [useCustom, setUseCustom] = useState(false);
  const [customMnemonic, setCustomMnemonic] = useState('');
  const [recipeId, setRecipeId] = useState(CURATED_RECIPES[0].id);
  const [result, setResult] = useState<CreateResultV3 | null>(null);
  const [error, setError] = useState<string | null>(null);

  const create = () => {
    setError(null);
    try {
      const mnemonic = useCustom ? customMnemonic.trim().toLowerCase() : FIXED_TEST_MNEMONIC;
      const date = new Date().toLocaleDateString('en-GB');
      setResult(createRecoveryPage(mnemonic, new SystemRNG(), recipeId, date));
    } catch (e) {
      setResult(null);
      setError(e instanceof Error ? e.message : 'creation failed');
    }
  };

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <div className="print:hidden space-y-6">
        <h1 className="text-xl font-semibold" data-testid="text-create-title">Create Recovery Page</h1>

        <div className="border rounded p-4 space-y-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={useCustom}
              onChange={(e) => setUseCustom(e.target.checked)}
              data-testid="checkbox-custom-mnemonic"
            />
            <span>
              Use a custom mnemonic — <strong className="text-red-700">WARNING: test use only.
              Never enter a mnemonic that controls real funds.</strong>
            </span>
          </label>
          {useCustom ? (
            <textarea
              className="w-full border rounded p-2 font-mono text-sm"
              rows={3}
              value={customMnemonic}
              onChange={(e) => setCustomMnemonic(e.target.value)}
              placeholder="24 words…"
              data-testid="input-custom-mnemonic"
            />
          ) : (
            <p className="text-sm text-gray-600 font-mono break-all" data-testid="text-fixed-mnemonic">
              Fixed test mnemonic: {FIXED_TEST_MNEMONIC}
            </p>
          )}
          <div className="flex items-center gap-2 text-sm">
            <span>Recipe body (carries zero payload):</span>
            <select
              className="border rounded p-1"
              value={recipeId}
              onChange={(e) => setRecipeId(e.target.value)}
              data-testid="select-recipe"
            >
              {CURATED_RECIPES.map((r) => (
                <option key={r.id} value={r.id}>{r.title}</option>
              ))}
            </select>
          </div>
          <button
            className="bg-black text-white rounded px-4 py-2 text-sm"
            onClick={create}
            data-testid="button-create"
          >
            Create
          </button>
          {error && <p className="text-red-600 text-sm" data-testid="text-create-error">{error}</p>}
        </div>

        {result && (
          <div className="border rounded p-4 space-y-2">
            <p className="text-sm font-medium">Vault Key (write it down — required for recovery):</p>
            <p className="font-mono text-sm break-all" data-testid="text-vault-key">{result.vaultKeyText}</p>
            <p className="text-sm font-medium">BIP32 master fingerprint:</p>
            <p className="font-mono text-sm" data-testid="text-fingerprint">{result.fingerprint}</p>
            <p className="text-sm text-gray-600" data-testid="text-print-note">
              Print the page below. The recipe is ordinary content; the entire payload lives in
              the footer string. Best-effort memory cleanup applies to typed arrays only —
              JavaScript strings cannot be zeroed.
            </p>
            <button
              className="border rounded px-4 py-2 text-sm"
              onClick={() => window.print()}
              data-testid="button-print"
            >
              Print
            </button>
          </div>
        )}

        {result && <Inspector result={result} />}
      </div>

      {result && (
        <div className="recovery-document border rounded p-6 bg-white" data-testid="text-recovery-document">
          <h2 className="text-lg font-semibold mb-2">{result.recipe.title}</h2>
          <div className="whitespace-pre-wrap text-sm leading-relaxed">{result.recipe.body}</div>
          <div className="mt-8 pt-2 border-t border-gray-200 text-[10px] text-gray-500 font-mono break-all" data-testid="text-footer-payload">
            {result.footer.lines.map((l, i) => (
              <div key={i}>{l}</div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/** Collapsible Inspector: codec parameters and payload facts. */
function Inspector({ result }: { result: CreateResultV3 }) {
  const [open, setOpen] = useState(false);
  const p = codecParams();
  return (
    <div className="border rounded p-4 print:hidden" data-testid="panel-inspector">
      <button className="text-sm underline" onClick={() => setOpen((s) => !s)} data-testid="button-toggle-inspector">
        {open ? 'Hide' : 'Show'} Inspector
      </button>
      {open && (
        <dl className="text-sm mt-3 grid grid-cols-2 gap-x-4 gap-y-1" data-testid="text-inspector-details">
          <dt>Capsule</dt>
          <dd>v2 — 49 bytes (AES-256-GCM-SIV, deterministic, no stored nonce)</dd>
          <dt>Error correction</dt>
          <dd>RS({p.n},{p.k}) over GF(2^8), {p.parity} parity bytes</dd>
          <dt>Correction budget</dt>
          <dd>2·errors + erasures ≤ {p.parity} (max {p.maxErasures} erasures / {p.maxErrors} errors)</dd>
          <dt>Payload token</dt>
          <dd>{p.tokenLength} Bech32 chars (sentinel + {p.dataChars} data + 6 checksum)</dd>
          <dt>Token (this page)</dt>
          <dd className="font-mono break-all">{result.token}</dd>
        </dl>
      )}
    </div>
  );
}
