import { useState } from 'react';
import { useLocation } from 'wouter';
import { SystemRNG } from '@/lib/crypto/rng';
import { decodeVaultKey } from '@/lib/crypto/vaultkey';
import { createShares, rejoinShares, ShareError } from '@/lib/crypto/shares';
import { wipe } from '@/lib/crypto/bytes';

/**
 * Shares page: split a Vault Key (CVK1.) into Independent Recovery shares
 * (CVSA1. / CVSB1.), and rejoin two shares back into the Vault Key.
 */
export default function SharesPage() {
  const [, navigate] = useLocation();

  // --- Split ---
  const [splitInput, setSplitInput] = useState('');
  const [splitResult, setSplitResult] = useState<{ shareA: string; shareB: string } | null>(null);
  const [splitError, setSplitError] = useState<string | null>(null);

  const split = () => {
    setSplitError(null);
    setSplitResult(null);
    try {
      const keyBytes = decodeVaultKey(splitInput.trim());
      const shares = createShares(keyBytes, new SystemRNG());
      wipe(keyBytes);
      setSplitResult(shares);
    } catch (e) {
      setSplitError(e instanceof Error ? e.message : 'split failed');
    }
  };

  // --- Rejoin ---
  const [shareA, setShareA] = useState('');
  const [shareB, setShareB] = useState('');
  const [rejoined, setRejoined] = useState<string | null>(null);
  const [rejoinError, setRejoinError] = useState<string | null>(null);

  const rejoin = () => {
    setRejoinError(null);
    setRejoined(null);
    try {
      setRejoined(rejoinShares(shareA, shareB));
    } catch (e) {
      setRejoinError(
        e instanceof ShareError || e instanceof Error ? e.message : 'rejoin failed',
      );
    }
  };

  return (
    <div className="max-w-3xl mx-auto p-6 space-y-8">
      <h1 className="text-xl font-semibold" data-testid="text-shares-title">
        Independent Recovery Shares
      </h1>
      <p className="text-sm text-gray-600">
        Split a Vault Key into two shares (Share A and Share B). Either share alone reveals
        nothing about the key; both together reconstruct it exactly. Store them in separate
        places.
      </p>

      <section className="border rounded p-4 space-y-3">
        <h2 className="font-medium">Split a Vault Key</h2>
        <label className="block text-sm">
          Vault Key (CVK1.)
          <textarea
            className="mt-1 w-full border rounded p-2 font-mono text-sm"
            rows={2}
            value={splitInput}
            onChange={(e) => setSplitInput(e.target.value)}
            placeholder="CVK1.XXXX XXXX ..."
            data-testid="input-split-key"
          />
        </label>
        <button
          className="px-4 py-2 border rounded text-sm hover:bg-gray-50"
          onClick={split}
          data-testid="button-split"
        >
          Create Shares
        </button>
        {splitError && (
          <p className="text-sm text-red-700" data-testid="text-split-error">
            {splitError}
          </p>
        )}
        {splitResult && (
          <div className="space-y-2">
            <div>
              <div className="text-xs text-gray-500">Share A</div>
              <code className="block break-all text-sm" data-testid="text-share-a">
                {splitResult.shareA}
              </code>
            </div>
            <div>
              <div className="text-xs text-gray-500">Share B</div>
              <code className="block break-all text-sm" data-testid="text-share-b">
                {splitResult.shareB}
              </code>
            </div>
            <p className="text-xs text-gray-500">
              Each share is a test secret. Never store both shares together.
            </p>
          </div>
        )}
      </section>

      <section className="border rounded p-4 space-y-3">
        <h2 className="font-medium">Rejoin Shares</h2>
        <label className="block text-sm">
          Share A (CVSA1.)
          <textarea
            className="mt-1 w-full border rounded p-2 font-mono text-sm"
            rows={2}
            value={shareA}
            onChange={(e) => setShareA(e.target.value)}
            data-testid="input-share-a"
          />
        </label>
        <label className="block text-sm">
          Share B (CVSB1.)
          <textarea
            className="mt-1 w-full border rounded p-2 font-mono text-sm"
            rows={2}
            value={shareB}
            onChange={(e) => setShareB(e.target.value)}
            data-testid="input-share-b"
          />
        </label>
        <button
          className="px-4 py-2 border rounded text-sm hover:bg-gray-50"
          onClick={rejoin}
          data-testid="button-rejoin"
        >
          Rejoin
        </button>
        {rejoinError && (
          <p className="text-sm text-red-700" data-testid="text-rejoin-error">
            {rejoinError}
          </p>
        )}
        {rejoined && (
          <div className="space-y-2">
            <div className="text-xs text-gray-500">Recovered Vault Key</div>
            <code className="block break-all text-sm" data-testid="text-rejoined-key">
              {rejoined}
            </code>
            <button
              className="px-4 py-2 border rounded text-sm hover:bg-gray-50"
              onClick={() => navigate('/recover')}
              data-testid="button-goto-recover"
            >
              Use in Recovery →
            </button>
          </div>
        )}
      </section>
    </div>
  );
}
