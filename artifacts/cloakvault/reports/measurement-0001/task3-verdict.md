# Task 3 — Verdict table (no recommendation; owner decides)

Honest capacity (Task 2, hygiene floors, conditioning rules respected):
single-sided front = **110 bits**, duplex sheet = 110 + 56 = **166 bits**.
Measured at the fixed typography (A4, 11pt serif, 20mm margins, single column):
front = 265 words, 45 wrapped lines, **1 page**; back sketch = 180 words, 1 page.
Front density: **0.42 bits per rendered word**.

| Codeword required | Single-sided (110 bits available) | Duplex (166 bits available) |
|---|---|---|
| Current: 968 bits (RS(121,93)) | does not fit — short by **858 bits** | does not fit — short by **802 bits** |
| v2: 512 bits (RS(64,49), confirmed Task 1) | does not fit — short by **402 bits** | does not fit — short by **346 bits** |

Method notes (facts only):
- Available bits are the honest per-slot sums from `task2-capacity-annotated.md`; the
  back-side sketch count carries ±10 bits of sketch-level uncertainty, which does not
  change any cell.
- For scale, the fitted honest densities imply a 512-bit codeword needs roughly
  1,200+ rendered words of *this* register (0.42 bits/word), i.e. about 4–5 duplex
  sheets — or a materially higher honest bits/word than a fully plausible recipe of
  this shape yields.
- grammar-test-0002 reached 1.45 bits/word only via ~28 ingredient lines, 12
  clone-skeleton steps and run-in prose — the properties the human gate failed.
