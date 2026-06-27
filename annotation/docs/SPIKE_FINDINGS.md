# LID Spike Findings (script-check → LID → merge)

Run: `uv run python annotation/spikes/lid_spike.py` (lingua 2.1.1; GlotLID model also
downloaded and available via huggingface `cis-lmu/glotlid`).

## Raw results (1 gold page each)

| Page | script-check coverage (non-punct) | residual tokens | token-LID τ≥0.5 TARGET/SOURCE |
|---|---|---|---|
| Chukchi-Russian (ext-Cyrillic source) | **68.8%** (99/144) | 45 | 13 / 32 |
| Na-Eng-Chi-Fr (IPA+Han) | 19.4% (85/438) | 353 | 121 / 232 |
| Canala-English (IPA+Latin) | 14.2% (49/344) | 295 | 98 / 197 |

## What it tells us

1. **Script-check coverage tracks the source script, as predicted — but only
   covers source tokens that *carry* a distinctive character.**
   - Extended-Cyrillic (Chukchi: ԓ ӄ ӈ) is a strong signal → 69% resolved.
   - IPA sources (Canala, Na) only get ~15-19%, because many source headwords
     are *plain Latin* (`ana`, `amu`, `nae`) with no IPA diacritic, so they fall
     into the residual and look just like English.

2. **Token-level LID is too noisy to trust.** Confirmed the known failure mode:
   single short words give almost no signal. lingua calls English `to`→Italian,
   `in`→German, `lie`→German, and real Chukchi headword `акватгыргын`→Russian 1.0
   (false positive). Per-token is the worst possible unit.

3. **Segment/run-level is better but still mixes** (Canala 22/41 runs TARGET).

## Revised tiering (supersedes the optimistic Tier-2 in mapping)

- **Non-Latin-script sources** (Bengali, Greek, Gujarati, Telugu, Khmer,
  Sanskrit, Georgian, Syriac, Yiddish, + Devanagari/Thai/etc.): script-check is
  ~100% decisive. **Deterministic. Confirmed.**
- **Extended-Cyrillic sources** (Chukchi, Evenki): script-check carries ~70%;
  small residual; pipeline viable with a Russian-vs-rest LID on the residual.
  **Pipeline OK.**
- **Latin / IPA sources** (Canala, Chepang, Reel, Ritharngu, Shilluk, Tiri,
  Efik, Iñupiatun, Nahuatl, Na): pure script+token-LID **underperforms** —
  plain-Latin source headwords are indistinguishable from English at the token
  level. The pipeline as drafted is NOT sufficient here.

## The fix for Latin/IPA sources: use entry STRUCTURE, not token LID

These dictionaries are line/entry-structured: **headword (source) first, then a
long definition (target)**. So:
  - headword = IPA-bearing token **OR** the leading token of an entry line → source
  - definition = the rest of the line/entry → one **run-level** LID call (reliable
    on long English/French runs), not per-token.
This positional rule was NOT in the spike (which tested pure script+token-LID,
the weakest version). It is the next thing to try before falling back to the LLM.

## Net recommendation

- Build the **deterministic path** for non-Latin sources now (low risk, ~half the
  corpus, no LID at all).
- For Latin/IPA sources, prototype the **structure-aware** variant (headword
  position + run-level LID) before committing; if it still mixes, use the LLM.
- Keep the **4 trilingual same-script dicts** (Circassian, Gojri, Vern. Syriac,
  and Na if structure-aware fails) on the **LLM** path.
