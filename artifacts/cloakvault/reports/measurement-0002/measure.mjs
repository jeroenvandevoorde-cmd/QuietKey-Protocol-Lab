// THROWAWAY ANALYSIS SCRIPT — measurement-0002 only. Not wired into build or tests.
// Page model: A4, 11pt serif, 20mm margins, single column → greedy wrap 88 chars/line,
// 51 lines/page (same model as the gate-packet generator and measurement-0001).
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

for (const [f, bits] of [['recipe-front.txt', 87], ['recipe-back.txt', 22]]) {
  const text = readFileSync(join(here, f), 'utf8');
  const words = text.split(/\s+/).filter(Boolean).length;
  const { lines, pages } = measure(text);
  console.log(`${f}: ${words} words, ${lines} wrapped lines, ${pages} page(s), ${(bits / words).toFixed(2)} bits/word at ${bits} bits`);
}
