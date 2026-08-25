# M19-R old-format morphology-reference registration

Authority: QK-DEC-103. Purpose: morphology reference only. These files are not
current QKA1 tokens and are never decode, profile, recovery, or Gate evidence.

The exact 48 rows are in `MORPHOLOGY-REFERENCES.tsv`.

| Set | Originals | Bytes | Canonical registry SHA-256 | Custody and commit |
| --- | ---: | ---: | --- | --- |
| spike | 29 | 59,148,370 | `4785158088a9c8a2b07a027c9e40078afeb36c77afe410ea25e829ed67d6ba60` | Git bytes introduced at `ba19eea82255f2434f6292c7939f9273d218184a` |
| Bridge | 19 | 58,847,212 | `8788fa92295f740c897e27051d904b31d7b0a28bf0d0ce037357b10132915eba` | canonical Replit bench, byte-verified at bench HEAD `60f98eb1633266bf58a36b5eb4a446baeb66974a`; GitHub mirrors that commit, not the JPEGs |

Each canonical registry digest is SHA-256 over rows in TSV order encoded as
`filename<TAB>decimal-byte-count<TAB>lowercase-sha256`, joined by LF with no
header and no final LF. The Bridge source manifest is
`artifacts/cloakvault/bridge/captures/CAPTURE-MANIFEST.json`, 19 rows, SHA-256
`227e3c0836f339b810d504751f21c45cf32fb277c31ddcf6d56be6efef4298f7`,
introduced at bench commit `94037946e7735c543a668227669c050a26ba466d`.

The spike evidence tree remains untouched. Three files are outside the 29-row
registration and are not deleted:

- `baseline-0-std-S01..jpeg`, 2,038,034 bytes, SHA-256
  `c8064f8ce898bcbfb64d8b52be3b361f662254e1781009fdf3ebb267f3dd23d3`,
  is the byte-identical double-dot duplicate of the registered single-dot file;
- `CloakVault capture-spike sheet v1.pdf`, a print source rather than a capture;
- `QuietKey_GateA_Spike_Verdict.pdf`, a report rather than a capture.

No image in either set is a fresh M19-R anchor or holdout. Registration does not
authorize Reader execution, synthetic fitting, scoring, or comparison-image
generation.
