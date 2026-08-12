// @vitest-environment jsdom
/**
 * End-to-end UI test for the Shares page: split a Vault Key into
 * CVSA1./CVSB1. shares through the rendered UI, then rejoin them and
 * verify the exact CVK1. string comes back. Also covers mismatch errors.
 */
import React from 'react';
import { describe, it, expect, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import SharesPage from '../shares';
import { generateVaultKey, encodeVaultKey } from '@/lib/crypto/vaultkey';
import { SystemRNG } from '@/lib/crypto/rng';

afterEach(cleanup);

function setValue(testId: string, value: string) {
  fireEvent.change(screen.getByTestId(testId), { target: { value } });
}

describe('Shares page (UI)', () => {
  it('splits a Vault Key and rejoins the shares back to the same key', async () => {
    const cvk = encodeVaultKey(generateVaultKey(new SystemRNG()));

    render(<SharesPage />);

    setValue('input-split-key', cvk);
    fireEvent.click(screen.getByTestId('button-split'));

    const shareA = (await screen.findByTestId('text-share-a')).textContent!;
    const shareB = (await screen.findByTestId('text-share-b')).textContent!;
    expect(shareA.startsWith('CVSA1.')).toBe(true);
    expect(shareB.startsWith('CVSB1.')).toBe(true);

    setValue('input-share-a', shareA);
    setValue('input-share-b', shareB);
    fireEvent.click(screen.getByTestId('button-rejoin'));

    await waitFor(() => {
      expect(screen.getByTestId('text-rejoined-key').textContent).toBe(cvk);
    });
  });

  it('shows an exact error when both inputs are the same share', async () => {
    const cvk = encodeVaultKey(generateVaultKey(new SystemRNG()));
    render(<SharesPage />);
    setValue('input-split-key', cvk);
    fireEvent.click(screen.getByTestId('button-split'));
    const shareA = (await screen.findByTestId('text-share-a')).textContent!;

    setValue('input-share-a', shareA);
    setValue('input-share-b', shareA);
    fireEvent.click(screen.getByTestId('button-rejoin'));

    const err = await screen.findByTestId('text-rejoin-error');
    expect(err.textContent).toMatch(/Share A/);
    expect(screen.queryByTestId('text-rejoined-key')).toBeNull();
  });

  it('rejects a bad Vault Key on split', async () => {
    render(<SharesPage />);
    setValue('input-split-key', 'CVK1.NOTAKEY');
    fireEvent.click(screen.getByTestId('button-split'));
    expect((await screen.findByTestId('text-split-error')).textContent).toBeTruthy();
  });
});
