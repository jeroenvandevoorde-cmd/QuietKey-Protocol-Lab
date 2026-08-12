# Measurement-0002 — Verdict table (no recommendation; owner decides)

Measured at the fixed typography (A4, 11pt serif, 20mm margins, single column;
88 chars/line, 51 lines/page model — `measure.mjs`):

- Front (`recipe-front.txt`): **272 words, 47 wrapped lines, 1 page** ✓ — real recipe
  layout, one ingredient per line, no run-in prose, no misspellings.
- Back (`recipe-back.txt`): 188 words, 1 page.
- Honest capacity (per-slot breakdown in `capacity-count.md`): **single side 87 bits**,
  **duplex 109 bits** as authored (≈137 upper bound if the back were a second dense
  recipe; that figure is an observation, not the count).
- Front density: **0.32 bits per rendered word** (vs 0.42 for the 0001 prose page —
  numeric lines are denser per line, but the page holds fewer slot positions; details in
  `capacity-count.md`).

Codeword derivation at the ~15% floor: parity quantizes to whole bytes, so the smallest
construction meeting the floor is **RS(57,49) = 456 bits** (16.33%). The 440-bit working
figure corresponds to 12.2% parity, below the floor; RS(56,49) = 448 bits is 14.29%, also
below. Both the target and derived figures are shown.

| Codeword required | Single side (87 bits) | Duplex as authored (109 bits) |
|---|---|---|
| 440 bits (prompt working figure, 12.2% parity — below floor) | does not close — short **353** | does not close — short **331** |
| **456 bits (RS(57,49), derived responsible floor)** | does not close — short **369** | does not close — short **347** |
| 512 bits (RS(64,49), full 30% parity, reference) | does not close — short **425** | does not close — short **403** |

Even against the duplex upper-bound observation (~137 bits), the smallest codeword is
short by ~303 bits. Fact for scale, not a recommendation: at the measured honest densities
(0.32–0.42 bits/word), 456 bits corresponds to roughly 1,100–1,400 rendered words of fully
plausible recipe text — about 4–6 A4 sides at this typography.

Measured, reported, stopped.
