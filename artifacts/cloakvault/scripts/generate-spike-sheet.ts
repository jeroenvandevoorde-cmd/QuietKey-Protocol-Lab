/**
 * CloakVault capture-spike measurement sheet generator (SHEET ONLY).
 *
 * Run: cd artifacts/cloakvault && npx tsx scripts/generate-spike-sheet.ts
 * Emits:
 *   spike/sheet.html   — two-page A4 printable (page 1: dense measurement
 *                        sheet T0–T4 + 50 mm scale bar; page 2: realistic
 *                        full recipe page with T5 in the real footer position)
 *   spike/tokens.json  — ground truth for T0–T5 (TEST SECRETS ONLY)
 *
 * Every token is genuine output of the frozen v3 codec (import-only reuse of
 * src/lib — no modifications). Typography is copied verbatim from the product
 * renderer so glyph size/shape matches what the product actually prints:
 *
 *   - Footer/token text: `font-mono text-[10px] text-gray-500 break-all` with
 *     a `border-t border-gray-200` rule (src/pages/create.tsx, footer block)
 *     where --app-font-mono = Menlo, monospace (src/index.css:145) and
 *     Tailwind text-[10px] = font-size 10px, text-gray-500 = #6b7280,
 *     border-gray-200 = #e5e7eb.
 *   - Page body: A4, 16 mm margins, Georgia/'Times New Roman' serif, 10.5pt,
 *     line-height 1.3 (src/index.css @media print, "density-ladder rung c").
 *
 * DETERMINISTIC: all inputs are fixed test values; re-running reproduces the
 * identical sheet.html and tokens.json byte-for-byte (fixed date string, no
 * clock or RNG anywhere).
 */
import { writeFileSync, mkdirSync } from 'node:fs';
import { bytesToHex } from '../src/lib/crypto/bytes';
import { createCapsuleV2 } from '../src/lib/crypto/capsule2';
import { encodeVaultKey } from '../src/lib/crypto/vaultkey';
import { encodePayload, wrapToken } from '../src/lib/codec/footer';
import { renderFooter, CURATED_RECIPES } from '../src/lib/pipeline';

// ── Fixed deterministic test inputs (TEST SECRETS ONLY, published on purpose) ─
// Distinct, human-auditable byte patterns per token: entropy byte j of token t
// is (0x10*(t+1) + j) mod 256; vault-key byte j is (0xA0 + 0x08*t + j) mod 256.
const TOKEN_IDS = ['T0', 'T1', 'T2', 'T3', 'T4', 'T5'] as const;

interface GroundTruth {
  id: string;
  entropy_hex: string;
  vault_key_hex: string;
  capsule_hex: string;
  token: string;
  wrapped_lines: string[];
}

const tokens: GroundTruth[] = TOKEN_IDS.map((id, t) => {
  const entropy = new Uint8Array(32).map((_, j) => (0x10 * (t + 1) + j) & 0xff);
  const vaultKey = new Uint8Array(32).map((_, j) => (0xa0 + 0x08 * t + j) & 0xff);
  const capsule = createCapsuleV2(entropy, vaultKey);
  const token = encodePayload(capsule);
  return {
    id,
    entropy_hex: bytesToHex(entropy),
    vault_key_hex: bytesToHex(vaultKey),
    capsule_hex: bytesToHex(capsule),
    token,
    wrapped_lines: wrapToken(token),
  };
});

// Fixed date so output is deterministic (matches the frozen-vector convention).
const PRINTED_DATE = '12/08/2026';
const T5 = tokens[5];
const t5Footer = renderFooter(T5.token, PRINTED_DATE);
const recipe = CURATED_RECIPES[0];

// Vault-key text lines are ground truth extras the harness may want.
const tokensJson = {
  _warning:
    'TEST SECRETS ONLY. CloakVault capture-spike ground truth. Published deliberately; never reuse any value with real funds.',
  sheet: 'cloakvault-capture-spike-sheet-v1',
  printedDate: PRINTED_DATE,
  page2: { recipeId: recipe.id, tokenId: 'T5', footerLines: t5Footer.lines },
  tokens: tokens.map((t) => ({ ...t, vault_key_text: encodeVaultKey(hexBytes(t.vault_key_hex)) })),
};

function hexBytes(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.slice(i * 2, i * 2 + 2), 16);
  return out;
}

const esc = (s: string) =>
  s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

// ── HTML ──────────────────────────────────────────────────────────────────────
// Token typography below is the PRODUCT footer rendering, not restyled:
// Menlo/monospace 10px #6b7280, break-all, 1px #e5e7eb top rule.
const tokenBlock = (t: GroundTruth) => `
    <div class="token-block">
      <div class="token-label">${t.id}</div>
      <div class="token-lines">${t.wrapped_lines.map((l) => `<div>${esc(l)}</div>`).join('')}</div>
    </div>`;

const html = `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>CloakVault capture-spike sheet v1</title>
<style>
  /* Print geometry copied from the product print stylesheet (src/index.css):
     A4, 16mm margins, 10.5pt Georgia serif, line-height 1.3. */
  @page { size: A4; margin: 16mm; }
  html, body { margin: 0; padding: 0; background: #fff; color: #000; }
  body { font-family: Georgia, 'Times New Roman', serif; font-size: 10.5pt; line-height: 1.3; }

  .page { page-break-after: always; }
  .page:last-child { page-break-after: auto; }

  .sheet-header { font-size: 12pt; font-weight: bold; margin: 0 0 2mm 0; }
  .sheet-sub { font-size: 9pt; color: #333; margin: 0 0 8mm 0; }

  /* Product footer typography (src/pages/create.tsx footer block +
     --app-font-mono in src/index.css). Do not restyle. */
  .token-lines {
    font-family: Menlo, monospace;   /* --app-font-mono */
    font-size: 10px;                 /* text-[10px] */
    color: #6b7280;                  /* text-gray-500 */
    word-break: break-all;           /* break-all */
  }
  .footer-rule { border-top: 1px solid #e5e7eb; /* border-t border-gray-200 */
                 margin-top: 8mm; padding-top: 2mm; }

  .token-block { margin-bottom: 30mm; /* ≥30 mm damage-isolation gap */ }
  .token-block:last-child { margin-bottom: 0; }
  .token-label { font-family: Menlo, monospace; font-size: 9pt; font-weight: bold;
                 color: #000; margin-bottom: 1mm; }

  /* 50 mm print-fidelity scale bar */
  .scale-wrap { margin: 0 0 10mm 0; }
  .scale-bar { position: relative; width: 50mm; height: 4mm;
               border: 0.4mm solid #000; box-sizing: border-box; }
  .scale-bar .tick { position: absolute; top: 0; width: 0.3mm; height: 2mm; background: #000; }
  .scale-label { font-size: 8pt; margin-top: 1mm; font-family: Menlo, monospace; }

  .recipe-title { font-size: 13pt; font-weight: bold; margin: 0 0 3mm 0; }
  .recipe-body { white-space: pre-wrap; }

  /* On-screen-only usage instructions (hidden in print). */
  .screen-note { border: 2px dashed #b45309; background: #fffbeb; color: #78350f;
                 font-family: Inter, sans-serif; font-size: 13px; line-height: 1.5;
                 padding: 14px 16px; margin: 0 0 24px 0; }
  .screen-note h2 { font-size: 14px; margin: 0 0 6px 0; }
  .screen-note ul { margin: 6px 0 0 18px; padding: 0; }
  @media print { .screen-note { display: none !important; } }
  @media screen { body { padding: 24px; max-width: 210mm; margin: 0 auto; } }
</style>
</head>
<body>

<div class="screen-note">
  <h2>Usage (screen only — not printed)</h2>
  <ul>
    <li>Print at <strong>100% scale</strong> (no “fit to page”). Before ANY session, verify the printed scale bar is exactly 50&nbsp;mm with a ruler; if not, the batch is invalid — reprint.</li>
    <li>Print ~15–20 identical copies of page&nbsp;1; page&nbsp;2 needs only 2–3 copies.</li>
    <li>One damage condition per copy, applied across T1–T4 (four replicates per condition). <strong>T0 is never touched</strong> — if T0 fails to read cleanly in a session, the session (lighting/focus) is at fault, not the damage: discard and reshoot.</li>
    <li>Photo filenames: <code>{damage}-{severity}-{lighting}-{copyNN}.jpg</code> (token identity comes from the printed T-labels, not the filename).</li>
  </ul>
</div>

<div class="page">
  <div class="sheet-header">CloakVault capture-spike sheet v1 · TEST TOKENS ONLY</div>
  <div class="sheet-sub">Sheet generated deterministically from the frozen v3 codec · date line: ______________ (fill in per session)</div>

  <div class="scale-wrap">
    <div class="scale-bar">
      <div class="tick" style="left: 10mm"></div>
      <div class="tick" style="left: 20mm"></div>
      <div class="tick" style="left: 30mm"></div>
      <div class="tick" style="left: 40mm"></div>
    </div>
    <div class="scale-label">50 mm — verify with a ruler before every session</div>
  </div>
${tokens.slice(0, 5).map(tokenBlock).join('\n')}
</div>

<div class="page">
  <div class="recipe-title">${esc(recipe.title)}</div>
  <div class="recipe-body">${esc(recipe.body)}</div>
  <div class="token-lines footer-rule">${t5Footer.lines.map((l) => `<div>${esc(l)}</div>`).join('')}</div>
</div>

</body>
</html>
`;

mkdirSync('spike', { recursive: true });
writeFileSync('spike/sheet.html', html);
writeFileSync('spike/tokens.json', JSON.stringify(tokensJson, null, 2) + '\n');
// Also publish the sheet through the dev server so it opens in a browser tab
// for printing (same bytes as spike/sheet.html).
mkdirSync('public/spike', { recursive: true });
writeFileSync('public/spike/sheet.html', html);

console.log('Wrote spike/sheet.html, public/spike/sheet.html and spike/tokens.json');
for (const t of tokens) {
  console.log(`${t.id}: ${t.token.slice(0, 8)} … ${t.token.slice(-8)}`);
}
