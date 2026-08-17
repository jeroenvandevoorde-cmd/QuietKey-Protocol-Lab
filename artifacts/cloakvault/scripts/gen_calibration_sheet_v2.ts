/**
 * calibration-sheet-production-v2 generator (owner Task 3).
 *
 * PRODUCTION-PATH PARITY: this generator does NOT re-style a lookalike.
 * It REUSES the actual production footer rendering code and configuration:
 *   - token wrapping:   wrapToken / FOOTER_WRAP_WIDTH  (src/lib/codec/footer.ts)
 *   - footer lines:     renderFooter                    (src/lib/pipeline.ts)
 *     (URL first line, raw wrapped lines, `&v=1` suffix, `Printed …` line)
 *   - footer DOM class: extracted VERBATIM at generation time from
 *     src/pages/create.tsx (build fails if the source drifts)
 *   - print stylesheet: the entire `@media print` block and the
 *     `--app-font-mono` declaration copied VERBATIM from src/index.css
 *
 * The ONLY intended difference from a real Recovery Document is the public,
 * deterministic calibration character sequence (no wallet secret involved).
 *
 * Output (refuses to overwrite):
 *   reader/calibration/sheets/calibration-sheet-production-v2-s<seed>.html
 *   reader/calibration/sheets/calibration-sheet-production-v2-s<seed>.groundtruth.json
 */
import { createHash } from 'node:crypto';
import { execSync } from 'node:child_process';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';

import { FOOTER_WRAP_WIDTH, SENTINEL, wrapToken } from '../src/lib/codec/footer';
import { renderFooter } from '../src/lib/pipeline';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const GENERATOR_ID = 'calsheet-production-v2';
const ALPHABET = 'qpzry9x8gf2tvdw0s3jn54khce6mua7l'; // exact Bech32 charset
const TOKEN_LEN = 142; // production token length (sentinel+data+checksum)
const COPIES_PER_CLASS = 71; // 32 * 71 = 2272 = 16 * 142 exactly
const N_FOOTERS = (32 * COPIES_PER_CLASS) / TOKEN_LEN; // 16
const PRINTED_DATE = '17/08/2026';

// ── deterministic PRNG (public seed; no wallet secret anywhere) ──────────
function mulberry32(seedStr: string): () => number {
  let h = 1779033703 ^ seedStr.length;
  for (let i = 0; i < seedStr.length; i++) {
    h = Math.imul(h ^ seedStr.charCodeAt(i), 3432918353);
    h = (h << 13) | (h >>> 19);
  }
  let a = h >>> 0;
  return () => {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * Balanced token set: every token starts with the production sentinel `cv0`
 * (so structural location behaves as on real footers), and GLOBAL class
 * counts are exactly COPIES_PER_CLASS for all 32 glyphs: the free-position
 * pool holds 71-16 copies of each sentinel glyph and 71 of the others.
 * NOTE: tokens are calibration content, NOT decodable production tokens —
 * no RS checksum validity (documented in ground truth); balance and the
 * production rendering path are what this sheet controls for.
 */
function balancedTokens(seed: string): string[] {
  const chars: string[] = [];
  for (const c of ALPHABET) {
    const n = COPIES_PER_CLASS - (SENTINEL.includes(c) ? N_FOOTERS : 0);
    for (let i = 0; i < n; i++) chars.push(c);
  }
  const rnd = mulberry32(`${GENERATOR_ID}:${seed}`);
  for (let i = chars.length - 1; i > 0; i--) {
    const j = Math.floor(rnd() * (i + 1));
    [chars[i], chars[j]] = [chars[j], chars[i]];
  }
  const free = TOKEN_LEN - SENTINEL.length;
  if (chars.length !== N_FOOTERS * free) throw new Error('internal: pool size mismatch');
  const tokens: string[] = [];
  for (let i = 0; i < N_FOOTERS; i++) {
    tokens.push(SENTINEL + chars.slice(i * free, (i + 1) * free).join(''));
  }
  return tokens;
}

// ── verbatim extraction from production sources (drift-proof) ────────────
function extractFooterClass(createTsx: string): string {
  const m = createTsx.match(
    /className="([^"]*)"\s+data-testid="text-footer-payload"/,
  );
  if (!m) throw new Error('production footer className not found in create.tsx — source drifted');
  return m[1];
}

function extractPrintCss(indexCss: string): string {
  const start = indexCss.indexOf('@media print {');
  if (start < 0) throw new Error('@media print block not found in index.css');
  let depth = 0;
  let i = indexCss.indexOf('{', start);
  for (; i < indexCss.length; i++) {
    if (indexCss[i] === '{') depth++;
    else if (indexCss[i] === '}') { depth--; if (depth === 0) break; }
  }
  return indexCss.slice(start, i + 1);
}

function extractMonoVar(indexCss: string): string {
  const m = indexCss.match(/--app-font-mono:[^;]+;/);
  if (!m) throw new Error('--app-font-mono not found in index.css');
  return m[0];
}

/** Pinned mapping of exactly the Tailwind utilities the production footer
 * uses. Regression-tested against the class string extracted from
 * create.tsx: any new/removed utility fails generation. */
export const FOOTER_UTILITY_CSS: Record<string, string> = {
  'mt-8': 'margin-top: 2rem;',
  'pt-2': 'padding-top: 0.5rem;',
  'border-t': 'border-top-width: 1px; border-top-style: solid;',
  'border-gray-200': 'border-top-color: #e5e7eb;',
  'text-[10px]': 'font-size: 10px;',
  'text-gray-500': 'color: #6b7280;',
  'font-mono': 'font-family: var(--app-font-mono);',
  'break-all': 'word-break: break-all;',
};

const FILLERS = [
  'Bring the milk to a gentle simmer over low heat, stirring occasionally so nothing catches on the bottom of the pan.',
  'Fold the dry ingredients into the batter in three additions, resting the mixture for ten minutes between folds.',
  'Season the stock to taste and let it reduce, uncovered, until it coats the back of a spoon.',
  'Set the dough somewhere warm and draft-free; it should double in size before shaping.',
];

function main(): void {
  const seedArg = process.argv.find((a) => a.startsWith('--seed='));
  const seed = seedArg ? seedArg.split('=')[1] : '20260817';

  const createTsx = fs.readFileSync(path.join(ROOT, 'src/pages/create.tsx'), 'utf8');
  const indexCss = fs.readFileSync(path.join(ROOT, 'src/index.css'), 'utf8');
  const footerClass = extractFooterClass(createTsx);
  const classes = footerClass.split(/\s+/).filter(Boolean);
  for (const c of classes) {
    if (!(c in FOOTER_UTILITY_CSS)) {
      throw new Error(`production footer uses unmapped utility "${c}" — update FOOTER_UTILITY_CSS deliberately`);
    }
  }
  const printCss = extractPrintCss(indexCss);
  const monoVar = extractMonoVar(indexCss);

  const tokens = balancedTokens(seed);
  if (tokens.length !== N_FOOTERS) throw new Error('internal: footer count mismatch');
  for (const t of tokens) {
    if (!t.startsWith(SENTINEL) || t.length !== TOKEN_LEN) throw new Error('internal: token shape');
  }
  const seq = tokens.join('');

  const footers = tokens.map((t) => renderFooter(t, PRINTED_DATE));
  // sanity: production wrapping reused, not re-implemented
  for (const [i, t] of tokens.entries()) {
    const w = wrapToken(t);
    if (w.length !== Math.ceil(TOKEN_LEN / FOOTER_WRAP_WIDTH)) throw new Error('wrap drift');
    if (!footers[i].lines[0].endsWith(w[0])) throw new Error('renderFooter drift');
  }

  const footerHtml = footers
    .map((f, i) => {
      const filler = `<div class="recipe-body">${FILLERS[i % FILLERS.length]}</div>`;
      const lines = f.lines.map((l) => `<div>${l}</div>`).join('\n        ');
      return `      ${filler}\n      <div class="${footerClass}" data-footer-index="${i}">\n        ${lines}\n      </div>`;
    })
    .join('\n');

  const utilityCss = classes
    .map((c) => `.${c.replace(/[^a-zA-Z0-9_-]/g, (ch) => `\\${ch}`)} { ${FOOTER_UTILITY_CSS[c]} }`)
    .join('\n');

  const html = `<!DOCTYPE html>
<!-- ${GENERATOR_ID} seed=${seed} — production-path calibration sheet.
     Footer class list, print stylesheet and mono font are copied verbatim
     from the production sources at generation time. Print at 100% scale,
     never fit-to-page, same printer/paper/settings as Bridge documents. -->
<html lang="en">
<head>
<meta charset="utf-8">
<title>CAL PRODUCTION V2 s${seed}</title>
<style>
:root { ${monoVar} }
body { margin: 0; }
h2 { font-size: 12pt; font-weight: 600; margin: 0 0 6mm; }
.recipe-body { margin: 0 0 4mm; }
/* footer utility classes — pinned production mapping (see generator) */
${utilityCss}
/* verbatim production print stylesheet (src/index.css) */
${printCss}
@media screen { .recovery-document { max-width: 178mm; margin: 8mm auto; font-family: Georgia, 'Times New Roman', serif; font-size: 10.5pt; line-height: 1.3; } }
</style>
</head>
<body>
  <div id="root">
    <div class="recovery-document">
      <h2>CAL PRODUCTION V2 · s${seed} · print 100% · no fit-to-page</h2>
${footerHtml}
    </div>
  </div>
</body>
</html>
`;

  const sha = (p: string) => createHash('sha256').update(fs.readFileSync(path.join(ROOT, p))).digest('hex');
  let commit = 'UNAVAILABLE';
  try { commit = execSync('git rev-parse HEAD', { cwd: ROOT }).toString().trim(); } catch { /* no repo */ }

  const classCounts: Record<string, number> = {};
  for (const c of seq) classCounts[c] = (classCounts[c] ?? 0) + 1;

  const groundtruth = {
    generator: GENERATOR_ID,
    seed,
    sheet_id: `${GENERATOR_ID}-s${seed}`,
    alphabet: ALPHABET,
    token_length: TOKEN_LEN,
    sentinel: SENTINEL,
    tokens_note: 'Every token starts with the production sentinel so structural location behaves as on real footers. Tokens are balanced calibration content, NOT decodable production tokens: no RS checksum validity. Global class counts are exactly balanced (sentinel occurrences included).',
    wrap_width: FOOTER_WRAP_WIDTH,
    printed_date: PRINTED_DATE,
    n_footers: N_FOOTERS,
    class_counts: classCounts,
    footers: footers.map((f, i) => ({
      index: i,
      token: tokens[i],
      lines_as_printed: f.lines,
      token_line_spans: [
        { line: 0, prefix_chars: f.lines[0].length - FOOTER_WRAP_WIDTH, token_chars: FOOTER_WRAP_WIDTH },
        { line: 1, prefix_chars: 0, token_chars: FOOTER_WRAP_WIDTH },
        { line: 2, prefix_chars: 0, token_chars: TOKEN_LEN - 2 * FOOTER_WRAP_WIDTH, suffix: '&v=1' },
      ],
    })),
    rendering_provenance: {
      source_commit: commit,
      footer_class_list: footerClass,
      footer_utility_css: FOOTER_UTILITY_CSS,
      print_css_copied_verbatim: true,
      reused_production_code: [
        'src/lib/codec/footer.ts (wrapToken, FOOTER_WRAP_WIDTH)',
        'src/lib/pipeline.ts (renderFooter: URL line, &v=1 suffix, Printed line)',
        'src/pages/create.tsx (footer className, extracted verbatim)',
        "src/index.css (@media print block + --app-font-mono, copied verbatim)",
      ],
      source_sha256: {
        'src/lib/codec/footer.ts': sha('src/lib/codec/footer.ts'),
        'src/lib/pipeline.ts': sha('src/lib/pipeline.ts'),
        'src/pages/create.tsx': sha('src/pages/create.tsx'),
        'src/index.css': sha('src/index.css'),
      },
      page: 'A4, 16mm margins (from production @page rule)',
      print_instruction: '100% scale, never fit-to-page, same printer/paper/settings as Bridge Recovery Documents',
    },
    provenance_rules: {
      bridge_hashes_prohibited: true,
      s46_development_replay_only: true,
      required_physical_print_copies: 2,
    },
  };

  const outDir = path.join(ROOT, 'reader/calibration/sheets');
  const base = path.join(outDir, `calibration-sheet-${GENERATOR_ID}-s${seed}`);
  for (const p of [`${base}.html`, `${base}.groundtruth.json`]) {
    if (fs.existsSync(p)) throw new Error(`refusing to overwrite ${p}`);
  }
  fs.writeFileSync(`${base}.html`, html);
  fs.writeFileSync(`${base}.groundtruth.json`, `${JSON.stringify(groundtruth, null, 2)}\n`);
  console.log('written:', `${base}.html`);
  console.log('written:', `${base}.groundtruth.json`);
}

const isMain = process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url);
if (isMain) main();

export { balancedTokens, extractFooterClass, extractPrintCss, extractMonoVar, GENERATOR_ID, ALPHABET, TOKEN_LEN, COPIES_PER_CLASS, N_FOOTERS };
