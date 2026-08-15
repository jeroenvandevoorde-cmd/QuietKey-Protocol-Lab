# Task 2 — Target artifact and honest capacity count (REPORT ONLY)

The front document (`target-front.txt`) was written by hand as camouflage first: real
recipe layout, 14 ingredient lines with a grouped sub-header, 6 short numbered steps, a
brief notes block. No encoding, no slots. The annotation below marks every position that
*could* carry bits under the standing rules, with honest lexicon sizes at the hygiene
floors (Levenshtein ≥ 3 inside without-replacement pools, ≥ 2 elsewhere), candidate sets
conditioned only on grammar + archetype (traybake), and all step/title/notes ingredient
mentions counted as zero-bit echoes. Bits per slot = floor(log2 |set|); the
without-replacement pool is floor(log2 of the falling factorial).

## Front side — per-slot annotation

### Header
| # | Position | Honest set | Bits |
|---|---|---|---|
| 1 | Title pattern ("X Roast Vegetable Traybake" vs 3 other patterns; ingredient references are echoes) | 4 | 2 |
| 2 | Description sensory pair ("smoky-sweet" — plausible glaze pairs at Lev≥2) | 8 | 3 |
| 3 | Description register phrase ("hands-off supper" variants) | 4 | 2 |
| 4 | Serves {2, 4, 6} | 3 | 1 |
| 5 | Total time line | echo of step times (must sum) | 0 |
**Header: 8 bits**

### Ingredients — "For the tray"
| # | Position | Honest set | Bits |
|---|---|---|---|
| 6 | Vegetable pool, without replacement, 5 slots (carrots/parsnips/potatoes/onions/cauliflower). Class-plausible traybake pool at Lev≥3: carrots, parsnips, potatoes, beetroot, squash, fennel, shallots, red onions, cauliflower, celeriac, turnips, sweet potatoes, leeks, peppers, mushrooms, courgettes = 16. 16·15·14·13·12 = 524,160 < 2^19 | falling factorial | 18 |
| 7–9 | Weight quantities ×3 (per-class 8-value sets, e.g. {400g…800g} in plausible steps) | 8 each | 9 |
| 10 | Onion count {1,2,3,4} | 4 | 2 |
| 11 | Cauliflower size {1 small, 1 large, half a large} | 3 | 1 |
| 12–16 | Prep phrases ×5 (per-class pools of 8: halved lengthways, quartered, thick wedges, roughly chopped, left whole, scrubbed, cubed, broken into florets — class-conditioned so nothing absurd) | 8 each | 15 |
| 17 | Oil {olive, rapeseed, sunflower, groundnut} | 4 | 2 |
| 18 | Oil qty {2,3,4 tbsp} | 3 | 1 |
| 19 | Flavour base (archetype-defining; harissa, chipotle paste, miso, pesto, tikka paste, chermoula, gochujang, romesco — Lev≥3 holds) | 8 | 3 |
| 20 | Base qty {1,2 tbsp} | 2 | 1 |
| 21 | Sweetener {honey, maple syrup, brown sugar, date syrup} | 4 | 2 |
| 22 | Sweetener qty {1 tbsp, 2 tsp} | 2 | 1 |
| 23 | Whole spice {cumin, coriander, fennel, caraway, mustard, nigella, ajwain, celery} seeds | 8 | 3 |
| 24 | Spice qty {1 tsp, 2 tsp} | 2 | 1 |
| 25 | Salt phrasing {half a teaspoon, a teaspoon} | 2 | 1 |
**Tray: 60 bits**

### Ingredients — "To finish"
| # | Position | Honest set | Bits |
|---|---|---|---|
| 26 | Citrus {lemon, orange} (lime–lemon and others fail plausibility-with-distance jointly; honest set is 2) | 2 | 1 |
| 27 | Cheese {feta, goat's cheese, ricotta salata, pecorino} | 4 | 2 |
| 28 | Cheese qty {75g, 100g} | 2 | 1 |
| 29 | Herb {parsley, coriander, dill, mint, basil, chives, tarragon, oregano} | 8 | 3 |
| 30 | Herb prep {roughly chopped, torn, leaves picked, finely chopped} | 4 | 2 |
| 31 | Nut/seed {almonds, hazelnuts, pistachios, walnuts, pine nuts, pecans, pumpkin seeds, sesame} | 8 | 3 |
| 32 | Nut qty {2,3 tbsp} | 2 | 1 |
**Finish: 13 bits**

### Steps (ingredient mentions are echoes = 0 bits throughout)
| # | Position | Honest set | Bits |
|---|---|---|---|
| 33 | Oven temp {190, 200, 210, 220} | 4 | 2 |
| 34 | Step-2 verb {tumble, tip, pile, spread} | 4 | 2 |
| 35 | Glaze adjective {glossy, coated, shiny, slick} | 4 | 2 |
| 36 | First roast time {20, 25, 30, 35} min | 4 | 2 |
| 37 | Toss phrase {toss once, turn once} | 2 | 1 |
| 38 | Second roast time {15, 20, 25} min | 3 | 1 |
| 39 | Doneness sensory {scorched in places, burnished, blistered, deeply browned, catching at the edges, caramelised, charred here and there, browned} | 8 | 3 |
| 40 | Knife-test object | echo of a tray vegetable | 0 |
| 41 | Finish verb {scatter, strew, shower, top} | 4 | 2 |
| 42 | Rest time {five, ten} minutes | 2 | 1 |
| 43 | Serve phrase {straight from the tray, at the table} | 2 | 1 |
**Steps: 17 bits**

### Notes
| # | Position | Honest set | Bits |
|---|---|---|---|
| 44 | Swap: target is an echo (0); replacement from tray pool minus used | 8 | 3 |
| 45 | Comparative {earthier, sweeter, milder, smokier, richer, lighter, sharper, nuttier} | 8 | 3 |
| 46 | Add-in {chickpeas, butter beans, cannellini, lentils, white beans, borlotti, halloumi, tofu} | 8 | 3 |
| 47 | Keeps {two, three} days | 2 | 1 |
| 48 | Serving idea {flatbreads, rice, couscous, toast} | 4 | 2 |
**Notes: 12 bits**

### FRONT TOTAL: **110 bits**

No inflation: everywhere a wider set was tempting (quantities especially), the honest
class-plausible count at the distance floor is what is written. The dominant earner is
the single without-replacement ingredient pool (18 bits); everything else averages
~1.9 bits per slot.

## Back side (`target-back.txt`) — same counting, sketch-level

| Section | Positions | Bits |
|---|---|---|
| Salad header (title pattern 2, sensory 3, serves 1) | 3 | 6 |
| Salad ingredients (pool of 12 crisp-salad items w/o replacement × 4 slots = floor log2(12·11·10·9) = 13; qty ×4 ≈ 6; prep ×4 ≈ 8) | 12 | 27 |
| Dressing (citrus 1, oil 2, oil qty 1, salt 1) | 4 | 5 |
| Salad steps (verb 2, bowl adj 1, hands phrase 1) | 3 | 4 |
| Variations paragraph (mild-tweak 3, crunch-timing 2, seasonal swap pair 3+3, second-roast time 1) | 5 | 12 |
| Scaling note (halve/for-two phrasing 1, browning phrase 1) | 2 | 2 |
**Back total: 56 bits** (sketch precision ±10; it is deliberately less polished)

## Measured word counts and density (script: `measure.mjs`, throwaway, not wired in)

Measured at the fixed typography model used throughout this project for A4 / 11pt serif /
20mm margins / single column: greedy wrap at 88 chars/line, 51 lines/page.

Run `node reports/measurement-0001/measure.mjs` to reproduce; results are pasted into
`task3-verdict.md` after the run.

- Front: words and page count → see verdict table (must be 1 page to qualify).
- Bits per rendered word, front: 110 / (front words).
- Duplex honest capacity: 110 + 56 = **166 bits**.
