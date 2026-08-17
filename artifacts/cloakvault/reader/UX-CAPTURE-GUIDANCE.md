# Capture guidance for recovery reads (Reader v0.2.1, Task 20)

Status: DEVELOPMENT note. Derived from Bridge Run 01 failure analysis
(11/19 images rejected for low sharpness — capture technique, not paper
damage, dominated the failure budget).

When the reader (or a future app flow) rejects a capture with
`CAPTURE_QUALITY_REJECT`, guide the user with:

1. **Tap to focus on the token block** (bottom of the page) before
   shooting; wait for focus lock.
2. **Fill the frame with the page**, all four corners visible, phone as
   parallel to the paper as practical.
3. **Use bright, indirect light.** Avoid flash (hotspot glare) and avoid
   your own shadow across the bottom of the page.
4. **Brace the phone** (two hands or rest on an object) — most rejects
   come from motion blur, not damaged paper.
5. **Flatten the page** on a plain, light-colored surface; a dark table
   directly under a curled page edge reduces contrast at the footer.
6. If rejects persist after several careful attempts, the document itself
   may be degraded — try stronger light at a slight angle to reduce gloss,
   and photograph the bottom third of the page filling the frame.

Reject reasons map to user actions:

| reason | user action |
| --- | --- |
| LOW_SHARPNESS | refocus, brace, more light |
| FOOTER_SIGNAL_TOO_WEAK | more light on bottom of page, remove shadow/glare, fill frame |
| FOOTER_LOCALIZATION_FAIL | flatten page, plain background, all corners in frame |
