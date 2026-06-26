The key refinement to your rule
Your heuristic (">2 languages AND >1 low-resource → LLM") is a good proxy, but the real discriminator is script separability, not language count. The question for each dictionary is: do the languages occupy distinguishable Unicode scripts?

If source script ≠ target script and there's no same-script romanization in the body → you don't even need LID. Script-check alone partitions it deterministically.
If source and one target share a script (IPA/Latin source vs English; extended-Cyrillic source vs Russian; or a romanization that collides with the target) → LID resolves it, because every target here is high-resource (English, Russian, French, Chinese). Your residual framing works perfectly.
LLM is only forced when ≥2 low/mid-resource languages share a script, so neither script-check nor LID can tell them apart.
This is why a "trilingual" dict isn't automatically LLM (Na's four languages sit in 3 distinguishable scripts + LID-separable English/French), and why a "bilingual" dict can still need LLM (none here do, but Cyrillic source-vs-Russian gets close).

The biggest cross-cutting finding: romanization
The languages "outside the directory name" are mostly not new languages — they're transliterations of the source in the target's script, plus a few genuine embedded languages. This romanization is the single thing that pushes a dict from deterministic → pipeline, because the romanized source collides with the target script:

Cyrillic-script romanization of Thai (Thai-Russian: саˆ-пˣракˇ)
Latin romanization of source (Punjabi páṇ, Kashmiri patsun, Malay A'kir, Japanese FUNADOIYA, Assyrian turi Babel-ki sa ana…)
Genuine embedded extra languages found: French glosses in Canala ("tourterelle verte") and Tiri ('buse chauve'); Hebrew + Arabic etymology refs in Assyrian (Heb. צור); Arabic + Greek refs in Syriac ([G. εἶτα]); Persian in Vernacular Syriac. All of these are either script-distinct (Hebrew/Arabic/Greek) or high-resource (French) — so LID/script handles them.

Per-dictionary mapping
Dictionary	Source script	Target(s)	Extra langs in body	Strategy	Tier
Bengalese-English	Bengali	English	—	script-check only	1 Deterministic
Greek-English	Greek	English	—	script-check only	1 Deterministic
Gujarati-English	Gujarati	English	—	script-check only	1 Deterministic
Khmer-English	Khmer	English	—	script-check only	1 Deterministic
Sanskrit-English	Devanagari	English	—	script-check only	1 Deterministic
Telugu-English	Telugu	English	—	script-check only	1 Deterministic
Georgian-Russian	Georgian	Russian (Cyrillic)	—	script-check (Georgian≠Cyrillic)	1 Deterministic
Syriac-English	Syriac	English	Arabic, Greek (refs)	script-check (all script-distinct)	1 Deterministic
Yiddish-English	Hebrew script	English	—	script-check only	1 Deterministic
Canala-English	IPA+Latin	English	French	char-check (IPA) → LID (En/Fr) → merge	2 Pipeline
Chepang-English	IPA+Latin	English	—	IPA char-check → LID → merge	2 Pipeline
Reel-English	IPA+Latin	English	—	IPA char-check → LID → merge	2 Pipeline
Ritharngu-English	IPA+Latin	English	cognate refs	IPA char-check → LID → merge	2 Pipeline
Shilluk-English	IPA+Latin	English	—	IPA char-check → LID → merge	2 Pipeline
Tiri-English	IPA+Latin	English	French	IPA char-check → LID (En/Fr) → merge	2 Pipeline
Efik-English	Latin+diacritics	English	—	diacritic check → LID → merge	2 Pipeline
Iñupiatun-English	Latin (ŋ ġ)	English	—	LID (is-English) → residual	2 Pipeline ⚠
Nahuatl-French	Latin+diacritics	French	—	LID (is-French) → residual	2 Pipeline
Chukchi-Russian	ext-Cyrillic (ԓ ӄ ӈ)	Russian	—	ext-char check → LID (is-Russian)	2 Pipeline ⚠
Evenki-Russian	ext-Cyrillic (ӣ ӯ)	Russian	Tungusic cognates	ext-char check → LID (is-Russian)	2 Pipeline ⚠
Malay-English	Jawi(Arabic) + roman	English	—	script (Jawi) + LID (Malay/En)	2 Pipeline
Kashmiri-English	Arabic + roman	English	—	script (Arabic) + LID → residual	2 Pipeline
Punjabi-English	Gurmukhi + roman	English	—	script (Gurmukhi) + LID for roman	2 Pipeline
Japanese-English	Kana/Kanji + romaji	English	—	script (Han/Kana) + LID for romaji	2 Pipeline
Thai-Russian	Thai + Cyrillic-roman	Russian	—	script (Thai) + LID (is-Russian)	2 Pipeline ⚠
Assyrian-English	Cuneiform + roman	English	Hebrew, Arabic	script (Cuneiform/Heb/Ar) + LID for roman	2 Pipeline ⚠
Circassian-Eng-Turkish	Arabic + roman	English, Turkish (Arabic/Ottoman)	—	Circassian & Turkish share Arabic script	3 LLM
Gojri-Eng-Hindi	Devanagari + roman	English, Hindi (Devanagari)	—	Gojri & Hindi share Devanagari	3 LLM
Vernacular Syriac-Ku/Tr-Eng	Syriac + roman	Kurdish/Turkish (Arabic), English	Persian	2 low-res + Arabic-script targets	3 LLM
Na-Eng-Chinese-French	IPA + Han	English, Chinese, French	—	scripts split 3 ways; LID splits En/Fr	2 Pipeline → LLM fallback ⚠
Totals: 9 deterministic · 17 pipeline · 4 LLM (⚠ = pipeline-eligible but the hardest cases — verify accuracy before trusting).

Notes on the borderline cases
Na-English-Chinese-French is the interesting one: four languages, but only Na is low-resource and it's IPA-distinct; Han splits Chinese; LID splits the high-resource English/French Latin spans. By script-separability it's pipeline-able. The risk is segmentation, not language ID — the inline 4-way density (¶ separators, tone marks, interleaved gloss order) is where it'll break. Treat as pipeline with an LLM fallback if the merge step produces noisy boundaries.
Cyrillic-source pairs (Chukchi, Evenki, Thai-Russian) are the riskiest Tier-2: source romanization/text shares Cyrillic with Russian. LID "is-Russian" is the separator and Russian is high-resource, so it should work — but this is exactly where I'd want numbers before trusting it.
The 4 LLM dicts all fail for the same reason: two languages sharing a script where at least one is low/mid-resource in that script (Ottoman Turkish in Arabic, Hindi in Devanagari, Kurdish/Turkish in Arabic). No script test and no LID can separate Gojri from Hindi when both are Devanagari.
Recommendation before we build
The Tier-2 ⚠ rows (Cyrillic pairs, Assyrian, Na) are the ones that decide whether the pipeline is worth it. I'd spike the LID separation on 3 representative pages — Canala (clean IPA+French), Chukchi (hard Cyrillic-vs-Russian), and Na (hard 4-way) — and measure binary target-detection precision/recall before committing the pipeline design. If Chukchi and Na hold up, the pipeline covers 26/30 and only the 4 genuinely-collided dicts need the LLM.

