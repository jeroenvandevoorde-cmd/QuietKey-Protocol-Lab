import { useState } from 'react';
import { recoverFromFooter, type RecoverResultV3 } from '@/lib/pipeline';

/**
 * Recover page (CloakVault v3): paste the printed footer payload string
 * (URL and all — extraction is structural), mark unreadable characters
 * with '?', enter the Vault Key.
 */
export default function RecoverPage() {
  const [pasted, setPasted] = useState('');
  const [vaultKey, setVaultKey] = useState('');
  const [result, setResult] = useState<RecoverResultV3 | null>(null);

  const recover = () => setResult(recoverFromFooter(pasted, vaultKey.trim()));

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-6">
      <h1 className="text-xl font-semibold" data-testid="text-recover-title">Recover</h1>

      <div className="border rounded p-4 space-y-3">
        <label className="text-sm font-medium" htmlFor="footer-input">
          Footer payload string (paste the whole footer line(s); replace characters you
          cannot read with <span className="font-mono">?</span> — the decoder never guesses):
        </label>
        <textarea
          id="footer-input"
          className="w-full border rounded p-2 font-mono text-sm"
          rows={4}
          value={pasted}
          onChange={(e) => setPasted(e.target.value)}
          placeholder="https://…/print?id=cv0…"
          data-testid="input-footer"
        />
        <label className="text-sm font-medium" htmlFor="vault-key-input">Vault Key:</label>
        <input
          id="vault-key-input"
          className="w-full border rounded p-2 font-mono text-sm"
          value={vaultKey}
          onChange={(e) => setVaultKey(e.target.value)}
          placeholder="CVK1.…"
          data-testid="input-vault-key"
        />
        <button
          className="bg-black text-white rounded px-4 py-2 text-sm"
          onClick={recover}
          data-testid="button-recover"
        >
          Recover
        </button>
      </div>

      {result && (
        <div className="border rounded p-4 space-y-3" data-testid="panel-result">
          {result.ok ? (
            <>
              <p className="text-green-700 font-semibold" data-testid="text-recover-ok">RECOVERED</p>
              <p className="text-sm font-medium">Mnemonic:</p>
              <p className="font-mono text-sm break-all" data-testid="text-recovered-mnemonic">{result.mnemonic}</p>
              <p className="text-sm font-medium">BIP32 master fingerprint (verify against creation):</p>
              <p className="font-mono text-sm" data-testid="text-recovered-fingerprint">{result.fingerprint}</p>
            </>
          ) : (
            <p className="text-red-700 font-semibold" data-testid="text-recover-failed">
              RECOVERY FAILED — {result.failure}
            </p>
          )}

          <div className="text-sm border-t pt-3 grid grid-cols-2 gap-x-4 gap-y-1" data-testid="text-decode-report">
            <span>Payload extracted</span>
            <span>{result.report.extracted ? `yes (${result.report.extractMethod})` : 'no'}</span>
            <span>Checksum</span>
            <span>
              {result.report.checksumValid === null
                ? 'unverifiable (erasure marks present)'
                : result.report.checksumValid
                  ? 'valid'
                  : 'INVALID (corruption detected before RS)'}
            </span>
            <span>RS decoded</span>
            <span>{result.report.decoded ? 'yes' : 'no'}</span>
            <span>Erasures used</span>
            <span data-testid="text-erasures">{result.report.erasuresUsed}</span>
            <span>Errors corrected</span>
            <span data-testid="text-errors">{result.report.errorsCorrected}</span>
            <span>Parity budget</span>
            <span data-testid="text-budget">
              2·{result.report.errorsCorrected} + {result.report.erasuresUsed} ={' '}
              {result.report.parityBudgetUsed} of {result.report.parityBudget}
            </span>
          </div>
        </div>
      )}
    </div>
  );
}
