// THROWAWAY ANALYSIS SCRIPT — measurement-0001 only. Not wired into build or tests.
// Word count + page measure at the fixed typography (A4, 11pt serif, 20mm margins,
// single column): greedy wrap at 88 chars/line, 51 lines/page — same model as the
// gate-packet generator.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));

function measure(text) {
  let lines = 0;
  for (const para of text.split('\n')) {
    if (!para.trim()) { lines += 1; continue; }
    let cur = 0;
    lines += 1;
    for (const word of para.split(/\s+/).filter(Boolean)) {
      const add = (cur === 0 ? 0 : 1) + word.length;
      if (cur + add > 88) { lines += 1; cur = word.length; } else { cur += add; }
    }
  }
  return { lines, pages: Math.ceil(lines / 51) };
}

for (const f of ['target-front.txt', 'target-back.txt']) {
  const text = readFileSync(join(here, f), 'utf8');
  const words = text.split(/\s+/).filter(Boolean).length;
  const { lines, pages } = measure(text);
  console.log(`${f}: ${words} words, ${lines} wrapped lines, ${pages} page(s)`);
}
console.log('front bits/word at 110 bits:', (110 / readFileSync(join(here, 'target-front.txt'), 'utf8').split(/\s+/).filter(Boolean).length).toFixed(2));
