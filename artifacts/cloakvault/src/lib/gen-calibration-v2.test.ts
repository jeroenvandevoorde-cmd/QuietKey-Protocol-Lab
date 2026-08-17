/**
 * Regression tests (owner Task 9): the production-path calibration sheet v2
 * generator must actually REUSE production footer configuration/code, not a
 * lookalike. These tests fail if the generated sheet drifts from the real
 * production sources.
 */
import { createHash } from 'node:crypto';
import * as fs from 'node:fs';
import * as path from 'node:path';
import { describe, expect, it } from 'vitest';

import {
  ALPHABET,
  COPIES_PER_CLASS,
  N_FOOTERS,
  TOKEN_LEN,
  balancedTokens,
  extractFooterClass,
  extractMonoVar,
  extractPrintCss,
  FOOTER_UTILITY_CSS,
} from '../../scripts/gen_calibration_sheet_v2';
import { FOOTER_WRAP_WIDTH, SENTINEL, wrapToken } from './codec/footer';
import { renderFooter } from './pipeline';

const ROOT = path.resolve(__dirname, '../..');
const SHEET_BASE = path.join(
  ROOT,
  'reader/calibration/sheets/calibration-sheet-calsheet-production-v2-s20260817',
);
const createTsx = fs.readFileSync(path.join(ROOT, 'src/pages/create.tsx'), 'utf8');
const indexCss = fs.readFileSync(path.join(ROOT, 'src/index.css'), 'utf8');
const html = fs.readFileSync(`${SHEET_BASE}.html`, 'utf8');
const gt = JSON.parse(fs.readFileSync(`${SHEET_BASE}.groundtruth.json`, 'utf8'));

describe('production-path calibration v2 — renderer reuse', () => {
  it('balanced deterministic tokens: production sentinel + 71 of each class overall', () => {
    const tokens = balancedTokens('20260817');
    expect(tokens.length).toBe(N_FOOTERS);
    for (const t of tokens) {
      expect(t.length).toBe(TOKEN_LEN);
      expect(t.startsWith(SENTINEL)).toBe(true);
    }
    const seq = tokens.join('');
    expect(seq.length).toBe(32 * COPIES_PER_CLASS);
    for (const c of ALPHABET) {
      expect(seq.split('').filter((x) => x === c).length).toBe(COPIES_PER_CLASS);
    }
    expect(balancedTokens('20260817')).toEqual(tokens); // deterministic
    expect(balancedTokens('other')).not.toEqual(tokens);
  });

  it('footer class list is extracted from create.tsx and fully mapped', () => {
    const cls = extractFooterClass(createTsx);
    expect(cls).toContain('font-mono');
    for (const c of cls.split(/\s+/).filter(Boolean)) {
      expect(FOOTER_UTILITY_CSS, `unmapped production utility "${c}"`).toHaveProperty(c);
    }
    // generated sheet uses the exact class string
    expect(html).toContain(`class="${cls}"`);
    expect(gt.rendering_provenance.footer_class_list).toBe(cls);
  });

  it('generated sheet embeds the production @media print block VERBATIM', () => {
    const block = extractPrintCss(indexCss);
    expect(block.startsWith('@media print {')).toBe(true);
    expect(html).toContain(block);
    expect(html).toContain(extractMonoVar(indexCss));
  });

  it('footer lines come from the production renderFooter/wrapToken path', () => {
    expect(gt.wrap_width).toBe(FOOTER_WRAP_WIDTH);
    for (const f of gt.footers) {
      const expected = renderFooter(f.token, gt.printed_date);
      expect(f.lines_as_printed).toEqual(expected.lines);
      expect(wrapToken(f.token).length).toBe(Math.ceil(TOKEN_LEN / FOOTER_WRAP_WIDTH));
      // every printed line group appears in the HTML
      for (const line of f.lines_as_printed) {
        expect(html).toContain(`<div>${line}</div>`);
      }
    }
  });

  it('recorded source hashes match the current production sources', () => {
    for (const [rel, recorded] of Object.entries(
      gt.rendering_provenance.source_sha256 as Record<string, string>,
    )) {
      const actual = createHash('sha256')
        .update(fs.readFileSync(path.join(ROOT, rel)))
        .digest('hex');
      expect(actual, `${rel} drifted since sheet generation — regenerate v2 sheet`).toBe(recorded);
    }
  });

  it('ground truth is balanced and carries provenance rules', () => {
    expect(Object.values(gt.class_counts)).toEqual(new Array(32).fill(COPIES_PER_CLASS));
    expect(gt.provenance_rules.bridge_hashes_prohibited).toBe(true);
    expect(gt.provenance_rules.required_physical_print_copies).toBe(2);
    expect(gt.provenance_rules.s46_development_replay_only).toBe(true);
  });
});
