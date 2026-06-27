# Tier routing decision (PRD Milestone 4)

Per PRD **D-1**, routing is a qualitative eyeball of script-check output — there is no
gold language-separation to score against. The judgment below was made by running the
Tier-1 script-check labeler over every gold page and inspecting the source/target split.

## Tier 1 — script-check labeler (9 dictionaries, 23 gold pages) — DONE

Source script is distinct from the single target script, so `classify_token` partitions
deterministically. Verified: every page yields a healthy, non-degenerate source/target
split (22–54% source / 46–78% target, no stray third language). `*_lang.json` maps
written next to each gold page (`labeled_via="heuristic"`, `rule_set="script-check-v1"`).

| Dictionary | Source script | Target | pages |
|---|---|---|---|
| Bengalese-English | Bengali | English | 3 |
| Greek-English | Greek | English | 3 |
| Gujarati-English | Gujarati | English | 3 |
| Khmer-English | Khmer | English | 3 |
| Sanskrit-English | Devanagari | English | 3 |
| Telugu-English | Telugu | English | 3 |
| Syriac-English | Syriac | English | 3 |
| Georgian-Russian | Georgian | Russian | 1 |
| Yiddish-English | Hebrew | English | 1 |

These are drafts for Label Studio review (D-5), but Tier-1 drafts should need near-zero edits.

## Tier 2 — LLM labeler (21 dictionaries) — PENDING (Milestone 5)

Source shares a script with a target (IPA/Latin vs English; extended-Cyrillic vs Russian;
romanization colliding with the target; or ≥2 same-script low-resource languages), so
script-check leaves the languages mixed — route to the LLM labeler.

```
Assyrian-English          Iñupiatun Eskimo-English   Punjabi-English
Canala-English            Japanese-English           Reel-English
Chepang-English           Kashmiri-English           Ritharngu-English
Chukchi-Russian           Malay-English              Shilluk-English
Circassian-English-Turkish Na-English-Chinese-French Thai-Russian
Efik-English              Nahuatl-French             Tiri-English
Evenki-Russian            Gojri-English-Hindi        Vernacular Syriac-Kurdish_Turkish-English
```

(= all 30 dictionaries minus the 9 Tier-1.)
