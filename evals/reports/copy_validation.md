# Copy validation

Run: 2026-11-17T22:28:11Z. Script: `evals/validate_copy.py`.

**Overall: PASS**

## Inputs this run validated against

The texts are hand-written against these exact files. If a pipeline rerun changes them, rerun this script:
it lists every text whose numbers no longer match.

- `outputs/one_pagers/facts_for_copy.json` md5 `09d1918efb0545e5cbbf967dfa1323d4` modified 2026-11-17T22:27:22Z
- `outputs/one_pagers/copy.json` md5 `163045f0f0c1f54ebb0ce456a2511cb1` modified 2026-11-16T20:52:02Z
- `outputs/targets/target_list.csv` md5 `ef2401d5375ea5b9c89738a4b6d4d73a` modified 2026-11-17T22:27:21Z
- `data/processed/rationales_llm.csv` md5 `63b2b3af236150e43c69d667b543b5f8` modified 2026-11-17T13:49:15Z

## What was checked

- `outputs/one_pagers/copy.json`: 20 keys matching `facts_for_copy.json`; exactly 3 bullets per account;
  each bullet one sentence of at most 38 words, no question; angle at most 60 words;
  three different product capabilities per account (keyword map in the script); no em or en dashes;
  no banned words; no exclamation marks; no group-level 'pays in' claims; opening words not reused more than 3 times.
- Every number in the text must equal a numeric value of that account's JSON (estimates block excluded,
  numbers in the why-now signal texts included) rounded to 0 or 1 decimals. Allowed extras: the benchmarks 30, 32, 60,
  the phrase 'about 20% of invoices' (share AP teams chase) and 'S/4HANA'.
- `data/processed/rationales_llm.csv`: 100 rows matching `target_list.csv`; 2 sentences, at most 45 words;
  same style checks; no currency amounts; every number equals a field value of the same row (estimate columns and URLs
  excluded, signal texts included) rounded to 0 or 1 decimals, sign expressed in words. Allowed extras: 30, 32, 60; the tier number is a row field.

## Result

| File | Items | Numbers checked | Errors | Result |
|---|---|---|---|---|
| copy.json | 20 accounts, 60 bullets | 179 | 0 | PASS |
| rationales_llm.csv | 103 rationales | 500 | 0 | PASS |

## Rules added after the assets review (internal assets review, not in the public copy)

- Rule 1 (late shares): if the group late share is null in the facts, no text of that account may argue from late payment;
  an entity whose late share is null or carries `pct_paid_late_note` may not be named in a text that cites a late share.
  The literal check 'no percentage equal to a nulled late share' is not feasible because the nulled value is no longer in the
  facts; the number check already rejects any percentage that is not a value of the account. Same null rule for rationales.
- Rule 2 (trend base): in multi-entity accounts a trend phrase needs 'n of m', 'both', 'all n' or a named entity in the same text.
- Rule 4 (rationales): the words score, scores, scored, tier are rejected.
- Rule 5: 'about 20% of invoices' in at most two accounts; 'one invitation', 'entity by entity' rejected.
- Rule 6: any mention of SAP or S/4HANA in the copy is rejected.
- 'weighted by invoice value' at most once per account.

## Not machine-checked

- Whether a correctly quoted number is attached to the right entity or metric (the check is on values, not on meaning).
- Absence of personal names (written by rule: roles only; entity names are company names from the statutory reports).
- Tone and neutrality beyond the banned-word list.
