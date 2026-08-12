/**
 * CloakVault v3 end-to-end pipeline: mnemonic ⇄ printed page with footer payload.
 *
 * Create:  mnemonic → 32B entropy → 49B capsule v2 (AES-256-GCM-SIV)
 *          → footer codec (RS(83,49) + Bech32 + checksum) → token
 *          → printable page = curated recipe body (zero payload) + fake
 *            browser-print footer carrying the wrapped token.
 * Recover: pasted footer text (+ Vault Key) → extract token → checksum
 *          → RS decode (erasure-aware, instrumented) → capsule → open
 *          → mnemonic + fingerprint.
 *
 * The body recipe and the footer payload are fully independent.
 */
import type { RNG } from '@/lib/crypto/rng';
import { createCapsuleV2, openCapsuleV2, Capsule2Error } from '@/lib/crypto/capsule2';
import { generateVaultKey, encodeVaultKey, decodeVaultKey } from '@/lib/crypto/vaultkey';
import { mnemonicToEntropy32, entropy32ToMnemonic, mnemonicToBip39Seed } from '@/lib/crypto/wallet';
import { masterFingerprintFromSeed, formatFingerprint } from '@/lib/crypto/fingerprint';
import { wipe } from '@/lib/crypto/bytes';
import {
  encodePayload,
  decodePayload,
  wrapToken,
  codecParams,
  RS_PARITY_BYTES,
  type DecodeReport,
} from '@/lib/codec/footer';
import { CURATED_RECIPES, recipeById, type CuratedRecipe } from '@/lib/recipes';

export { CURATED_RECIPES, codecParams, RS_PARITY_BYTES };

/** Fake print-footer domain — looks like machine exhaust, carries no meaning. */
export const FOOTER_DOMAIN = 'arecipeforamaster.com';

export interface FooterBlock {
  /** Lines exactly as printed at the bottom of the page. */
  lines: string[];
  token: string;
}

/** Render the sloppy-browser-print footer for a payload token. */
export function renderFooter(token: string, printedDate: string): FooterBlock {
  const wrapped = wrapToken(token);
  const lines: string[] = [];
  lines.push(`https://${FOOTER_DOMAIN}/print?id=${wrapped[0]}`);
  for (let i = 1; i < wrapped.length; i++) lines.push(wrapped[i]);
  lines[lines.length - 1] += '&v=1';
  lines.push(`Printed ${printedDate} · page 1 of 1`);
  return { lines, token };
}

export interface CreateResultV3 {
  vaultKeyText: string;
  fingerprint: string;
  capsule: Uint8Array; // 49-byte capsule (Inspector)
  token: string; // full payload token
  recipe: CuratedRecipe;
  footer: FooterBlock;
}

export function createRecoveryPage(
  mnemonic: string,
  rng: RNG,
  recipeId: string = CURATED_RECIPES[0].id,
  printedDate: string = '12/08/2026',
): CreateResultV3 {
  const entropy = mnemonicToEntropy32(mnemonic);
  const vk = generateVaultKey(rng);
  try {
    const vaultKeyText = encodeVaultKey(vk);
    const capsule = createCapsuleV2(entropy, vk);
    const token = encodePayload(capsule);
    const seed = mnemonicToBip39Seed(mnemonic);
    const fingerprint = formatFingerprint(masterFingerprintFromSeed(seed));
    wipe(seed);
    return {
      vaultKeyText,
      fingerprint,
      capsule,
      token,
      recipe: recipeById(recipeId),
      footer: renderFooter(token, printedDate),
    };
  } finally {
    wipe(entropy);
    wipe(vk);
  }
}

export interface RecoverResultV3 {
  ok: boolean;
  mnemonic: string | null;
  fingerprint: string | null;
  report: DecodeReport;
  failure: string | null; // single RECOVERY FAILED reason bucket
}

export function recoverFromFooter(pastedText: string, vaultKeyText: string): RecoverResultV3 {
  const report = decodePayload(pastedText);
  if (!report.decoded || !report.capsule) {
    return { ok: false, mnemonic: null, fingerprint: null, report, failure: report.failure ?? 'decode failed' };
  }
  let vk: Uint8Array;
  try {
    vk = decodeVaultKey(vaultKeyText);
  } catch {
    return { ok: false, mnemonic: null, fingerprint: null, report, failure: 'invalid Vault Key' };
  }
  try {
    const entropy = openCapsuleV2(report.capsule, vk);
    const mnemonic = entropy32ToMnemonic(entropy);
    const seed = mnemonicToBip39Seed(mnemonic);
    const fingerprint = formatFingerprint(masterFingerprintFromSeed(seed));
    wipe(seed);
    wipe(entropy);
    return { ok: true, mnemonic, fingerprint, report, failure: null };
  } catch (e) {
    const msg = e instanceof Capsule2Error ? 'authentication failed (wrong key or damaged payload)' : 'recovery failed';
    return { ok: false, mnemonic: null, fingerprint: null, report, failure: msg };
  } finally {
    wipe(vk);
  }
}
