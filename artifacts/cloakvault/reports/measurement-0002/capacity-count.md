# Measurement-0002 — Numeric-register honest capacity count (REPORT ONLY)

## Codeword derivation at the ~15% responsible floor

Payload: 256-bit seed + 128-bit tag + 8-bit version = **392 bits = 49 bytes** (byte-aligned,
matches the confirmed v2 capsule from measurement-0001).

RS symbols are bytes in the standing GF(2^8) construction, so parity quantizes to whole
bytes:
- 15% of 49 = 7.35 → **7 parity bytes = 14.29%**, which is *below* the stated floor
  ("~15 percent, not lower"), giving RS(56,49) = 448 bits.
- The smallest parity meeting the floor is **8 bytes = 16.33% → RS(57,49), codeword
  456 bits**.

The 440-bit target in the prompt corresponds to 6 parity bytes (12.2%), below the floor.
**Derived responsible-floor codeword: RS(57,49), 456 bits** (delta +16 vs the 440-bit
working figure; cause: byte-symbol parity quantization). Both 440 and 456 appear in the
verdict table, plus the 512-bit full-parity reference.

## Archetype choice

Baking/pantry archetypes were compared for honest numeric entropy. A crumble cake carries
~14 weighed lines but its quantities are ratio-coupled by plausibility (flour/butter/sugar
must roughly balance), which caps honest per-slot ranges. **Granola** was chosen: it is the
plausibility-maximal numeric archetype — every one of ~19 ingredient lines carries a weight
with a genuinely wide tolerated range, and it supports three without-replacement identity
pools (nuts, seeds, dried fruit) at Levenshtein ≥ 3. No run-in prose; one item per line.

## Front side (`recipe-front.txt`) — per-slot annotation

Granularity rule applied throughout: only steps a printed recipe actually shows
(25 g steps for weights ≥50 g, 20 ml for syrups/oils, 5 min for times, 10°C for ovens,
{1/4, 1/2, 1, 2} tsp for spices). Bits = floor(log2 |set|); pools = floor(log2 falling
factorial). Echoes and derived fields = 0.

### Header
| Position | Plausible set and justification | Bits |
|---|---|---|
| Yield {800 g, 1 kg, 1.2 kg} — what granola recipes state | 3 | 1 |
| Hands-on {10, 15, 20} min | 3 | 1 |
| Bake time / oven | echo of steps 5 and 1 (header must match) | 0 |
**Header** | | **2** |

### Dry group
| Position | Set / range @ granularity | Bits |
|---|---|---|
| Oats 250–400 g @ 25 g (7 values; finer is not printed) | 7 | 2 |
| Flake identity {rye, barley, spelt, quinoa} | 4 | 2 |
| Flake weight 50–150 g @ 50 g | 3 | 1 |
| Coconut/extra {coconut flakes, buckwheat groats} | 2 | 1 |
| Coconut weight {25, 50, 75} g | 3 | 1 |
| Nut pool w/o replacement, k=3 of {almonds, hazelnuts, pecans, walnuts, pistachios, cashews, brazils, macadamias, peanuts} (pairwise Lev ≥ 3 verified by eye) → 9·8·7 = 504 | 504 | 8 |
| Nut weights ×3, each 50–125 g @ 25 g (4 values) | 4 each | 6 |
| Nut preps ×3, class sets {whole, roughly chopped, halved, flaked} | 4 each | 6 |
| Seed pool w/o replacement, k=3 of {pumpkin, sunflower, sesame, flax, poppy, hemp, chia} → 7·6·5 = 210 | 210 | 7 |
| Seed weights ×3, each 25–75 g @ 25 g | 3 each | 3 |
| Spice 1 identity (8-item ground-spice pool) | 8 | 3 |
| Spice 1 quantity {1/2, 1, 2} tsp | 3 | 1 |
| Spice 2 identity (pool minus spice 1 → 7) | 7 | 2 |
| Spice 2 quantity {1/4, 1/2, 1} tsp | 3 | 1 |
| Salt {1/4, 1/2} tsp | 2 | 1 |
**Dry** | | **45** |

### Wet group
| Position | Set / range | Bits |
|---|---|---|
| Syrup {maple syrup, honey, agave, date syrup} | 4 | 2 |
| Syrup volume 60–120 ml @ 20 ml | 4 | 2 |
| Oil {sunflower, coconut, rapeseed, olive} | 4 | 2 |
| Oil volume 40–80 ml @ 20 ml | 3 | 1 |
| Sugar {light brown, demerara, coconut, golden caster} | 4 | 2 |
| Sugar weight {25, 50, 75} g | 3 | 1 |
| Extract {vanilla, almond} | 2 | 1 |
**Wet** | | **11** |

### To finish
| Position | Set / range | Bits |
|---|---|---|
| Dried-fruit pool w/o replacement, k=2 of {raisins, apricots, cranberries, cherries, figs, dates, mango, apple rings} → 56 | 56 | 5 |
| Fruit weights ×2, 75–150 g @ 25 g (4 values) | 4 each | 4 |
| Apricot prep {chopped, left whole} | 2 | 1 |
| Zest {orange, lemon} | 2 | 1 |
**Finish** | | **11** |

### Method (all ingredient mentions are echoes = 0)
| Position | Set / range | Bits |
|---|---|---|
| Trays {one, two} (coupled to volume, still honestly free) | 2 | 1 |
| Warm time {1, 2, 3} min | 3 | 1 |
| Press phrase {press down firmly, press flat} | 2 | 1 |
| Bake 30–45 min @ 5 (4 values) | 4 | 2 |
| Stir-at time {15, 20, 25} min (must precede bake end) | 3 | 1 |
| Doneness {deep golden, dark amber, richly browned, golden brown} | 4 | 2 |
| Ordinary verb/phrase choices ×2 (floor-2 sets) | 2 each | 2 |
**Method** | | **10** |

### Notes
| Position | Set / range | Bits |
|---|---|---|
| Nut suggestion: unordered pair from the 6 unused pool nuts → C(6,2)=15 | 15 | 3 |
| Fruit swap from 6 unused pool fruits | 6 | 2 |
| Comparative {sharper, sweeter, richer, darker} | 4 | 2 |
| Keeps {2, 3, 4} weeks | 3 | 1 |
**Notes** | | **8** |

### FRONT TOTAL: **87 bits**

Breakdown by source class: numeric quantities/temps/times **32**, ingredient identities
(pools + small identity sets) **36**, method/technique choices **9**, notes **8**, header **2**.

## Back side (`recipe-back.txt`)

| Section | Positions (same rules) | Bits |
|---|---|---|
| Bircher: granola wt {40,50,60}=1, yoghurt {75,100,125}=1, milk {50,75,100}=1, fruit {apple, pear}=1, honey {1 tsp, 2 tsp}=1, overnight phrase=1 | 6 | 6 |
| Warm pears: fruit {pears, apples, plums, peaches}=2, count {2}=0 (fixed by serves), butter {10,15,20}=1, fry time {4,6,8}=1, heat {medium, medium-high}=1, spoon qty {2,3 tbsp}=1 | 6 | 6 |
| Topping: weight {50,75,100}=1, last-{5,10,15} min=1, comparative phrase (4)=2 | 3 | 4 |
| Keeping/swaps: fruit pair from unused pool (C(6,2)=15)=3, nut-free bake-adjust {5,10} min=1, keeps weeks {2,3,4}=1, freezer months {1,2,3}=1 | 4 | 6 |
**Back total** | | **22** |

The back side is honest but thin: variation pages are mostly prose and echoes. A second
full recipe in place of the variations page would raise it to roughly front-minus-pools
(~45–55 bits) at the cost of "two unrelated full recipes on one card" plausibility — noted
as an observation, not counted.

**Duplex total (as authored): 87 + 22 = 109 bits.**
(Upper bound if the back were a second dense granola-register recipe: ≈ 87 + 50 = ~137.)

## Measured word counts (script: `measure.mjs`, throwaway)

At the fixed typography (A4, 11pt serif, 20mm margins, single column; 88 chars/line,
51 lines/page model): see run output in `verdict.md`. Front must measure 1 page.

## Density comparison vs measurement-0001

- Prose register (0001): 110 bits / 265 words = **0.42 bits/word**.
- Numeric register (0002 front): 87 bits / ~250 words = **~0.35 bits/word** as measured —
  see verdict for exact words. Per *line*, numeric ingredient lines are denser (≈3.1
  bits/line vs ≈2.4 prose), but the numeric page holds fewer total slot positions: prose
  preps/adjectives contributed 15+ bits that metric lines don't plausibly carry, and the
  0001 front had a larger without-replacement pool spend (18 bits over 5 slots vs 15 over 6).
- Honest conclusion of the comparison: the numeric register is denser *locally* but does
  not raise the per-page honest total; both registers land in the ~90–110 bit band for a
  fully plausible A4 side. No inflation was applied to move either number.
