# Entity resolution check: UK reporting entities to parent groups

Checked by the `qa` agent on 2026-11-16, in two rounds. The checker did not build the matching and did not edit the pipeline or the data.

**Round 2 result: the 0.95 precision bar is met on the fresh sample.** 60 of 60 new links are correct (precision 1.000). Round 1 had failed at 0.833; the roll-up was rewritten in between. With 60 correct out of 60, the one-sided 95% lower confidence bound on precision is about 0.951, so the sample supports "at or above 0.95" only just. Precision is not recall: the stricter rules cut the map from 2,897 to 2,086 links, and 18 links that round 1 had confirmed as correct are no longer linked.

Gold file: `evals/gold/entity_matches.csv` (120 rows: `round` 1 and 2).

## Round 2: fresh sample from the rewritten map

### What changed between the rounds (as described by the pipeline owner)

- A link now needs an exact name match, or an unbroken chain of majority holdings (more than 50% at every step) in the Companies House PSC bulk data up to a name-matched universe company, with the nearest match winning. Investor and bank parents need a name link.
- Brand-prefix links are allowed only when the entity has no corporate owner on record.
- Wikidata links are corroboration only, no longer a link method.
- The "Mitsubishi" group-of-companies record is excluded.

Effect on the round-1 gold rows, re-checked by me against the current map: 32 of the 60 are still linked and all 32 point to the expected group. All 10 round-1 errors are gone. 18 correct round-1 links were dropped as well.

### What was checked

- Sample: `evals/gold/entity_matches_sample_v2.csv`, 60 links from the new map, stratified, seed 20261117, no overlap with round 1: 40 `ch_psc_chain`, 10 `exact_name`, 10 `brand_prefix`. All 60 are in the current map (2,086 links: 1,858 chain, 201 exact name, 27 brand prefix).
- Same verdict rules as round 1: joint ventures, minority stakes, former parents and independent network member firms count as wrong.
- Method: the live Companies House PSC page of each of the 60 entities (one fetch each, corporate controllers only, no individuals recorded), plus a second source where I could find one within the fetch budget: Wikipedia, the group's own website, a government registry or trade press. About 90 fetches and searches in total.

### Results

| Scope | Correct | Incorrect | Unverifiable | Precision |
|---|---|---|---|---|
| Round 2, all 60 | 60 | 0 | 0 | 1.000 |
| `ch_psc_chain` | 40 | 0 | 0 | 1.000 |
| `exact_name` | 10 | 0 | 0 | 1.000 |
| `brand_prefix` | 10 | 0 | 0 | 1.000 |

By confidence: 0.95 gives 28/28, 0.90 gives 22/22, 0.80 gives 10/10.

Incorrect rows: none.

Statistical reading: 60/60 gives a one-sided 95% lower bound of about 0.951 for the sampled mix. For the chain method alone (40/40, which is 89% of the map) the lower bound is about 0.93. The point estimate meets the bar; the sample is too small to prove 0.95 for the chain method on its own.

### Second sources

24 of 60 rows have a second source beyond the register:

- `ch_psc_chain`: 16 of 40 (12 Wikipedia, 2 the group's or company's own site, 1 trade press, 1 Wikipedia plus press).
- `brand_prefix`: 7 of 10 (company sites, a government registry, Wikipedia).
- `exact_name`: 1 of 10.

For 10 of the 40 chain rows the live register names the group's top company directly as the 75%+ owner. For the other 30, the first hop was confirmed live and the upper hops come from the pipeline's bulk-data chain; in 11 of those 30 a second source confirms the top of the chain. That leaves 19 chain rows that rest on the first hop plus group-named intermediate companies (for example Shell, Babcock, Persimmon, Tesco, Rio Tinto subsidiaries).

### Rows that are correct but worth knowing about

- 04612748 Amec Foster Wheeler Group → John Wood Group plc. Wood is the controlling parent, but Wood itself has been owned by Sidara since March 2026. Sidara is not in the universe. Any group-level statement about Wood should say so.
- 05340126 TT Games → Skydance Corp. Correct only since 6 October 2026, when Paramount closed its acquisition of Warner Bros. Discovery. The link is right; the universe revenue for that record may predate the merger.
- 10398354 Inovyn Europe → Ineos. The chain runs through INEOS Quattro and INEOS Industries, sister companies of INEOS Group Holdings. Correct for Ineos as a whole, not for INEOS Group Holdings as a legal entity.
- 02688514 MAN Truck and Bus UK → MAN Truck & Bus. The universe record is itself a TRATON / Volkswagen subsidiary.
- OC369329 Travis Perkins Plumbing & Heating LLP. The register shows Travis Perkins control; I did not check whether this LLP still trades after the 2021 sale of the plumbing and heating business.
- Three brand-prefix rows (Ferrero UK, Kimberly-Clark Europe, Dassault Systemes UK) rest on a ceased register entry for the group plus an unambiguous name, with no second source.

### Combined view

| Set | Rows | Correct | Precision |
|---|---|---|---|
| Round-1 rows still linked in the current map | 32 | 32 | 1.000 |
| Round-2 rows | 60 | 60 | 1.000 |
| Combined | 92 | 92 | 1.000 |

The 32 round-1 survivors are 19 chain, 6 exact name, 4 originally Wikidata company number and 3 brand prefix. They are not a fresh random sample of the new map, since the rules were rewritten with the round-1 errors known, so the combined figure is supporting evidence and not an independent estimate. Round 2 alone is the clean test.

### The cost: recall

18 links that round 1 verified as correct are no longer in the map. Examples: Booking.com Transport (Booking Holdings), Liverpool Victoria Insurance (Allianz), Towers Watson (WTW), Santander Fintech, Bureau Veritas Certification UK, Open Text UK, FedEx UK, EDF Trading (the register names EDF SA directly as 75%+ owner), Toyota Financial Services (UK), BMG Rights Management (UK). That is 18 of 50 correct round-1 links, 36%, in a sample that overweighted the small methods. The map shrank from 2,897 to 2,086 links. This check does not measure recall, but the round-1 rows show the new rules drop real subsidiaries of target groups, which lowers UK coverage for those groups.

### Limits

- Same as round 1: for chain links the register is the pipeline's own source, so without a second source the check verifies the walk and the name match, not ownership. 16 of 40 chain rows have a second source.
- Upper chain hops were not re-walked on the live register. In round 1 a command that fetched intermediate parents' register pages was denied by the user; I did not retry that in either round.
- Several second sources are search-result level (a result snippet from the company's own site or a registry) and were not opened in full: Kinto UK, Volvo Car UK, MAN Truck and Bus UK, Amadeus IT Services UK, Huawei Global Finance (UK), Danish Crown UK. One Red Bull Technology source is indirect. The notes column says which.
- 60 rows cannot show a rare failure pattern. Chains that end at private equity owners or consortiums, the pattern behind several round-1 errors, did not appear in this sample at all, so the new investor rule is untested here.
- No row is unverifiable, but a few steps rest on general knowledge (for example that IAA belongs to RB Global, that British Aluminium Limited is a Howmet company).

### Verdict and recommendation

The 0.95 bar is met on round 2 (60/60). It is fair to report "precision 1.00 on a fresh 60-link sample, lower bound about 0.95", and not fair to report it as proven for every method separately.

1. Report precision together with the coverage cost: the map lost 28% of its links, including verified correct ones.
2. Recover recall where it is safe: a direct register entry naming a universe company as 75%+ owner (EDF Trading, Eaton, Santander Fintech cases) should link. Check why those were dropped; it looks like a name-match gap, not a control gap.
3. Hand-check all 27 `brand_prefix` links. It takes minutes and removes the weakest stratum from the uncertainty.
4. Draw a targeted sample of chain links whose top company is an investor, bank or holding vehicle to test the new investor rule, since the random sample contained none.
5. Add a note field for groups that changed owner recently (Wood under Sidara, Warner Bros. under Skydance) so one-pagers do not describe the wrong ultimate parent.
6. Review by hand: the judgement calls in the gold file (Inovyn, Wood, MAN, and the round-1 calls).

## Round 1 (history): 0.833, failed

Round 1 checked the first version of the roll-up. Result: 50/60 = 0.833 on all sampled links, 48/58 = 0.828 on the links then in the map. The bar of 0.95 was not met. The findings below are kept as written at the time; "current map" in this section means the round-1 map of 2,897 links.

### What was checked


Whether each automatically linked UK legal entity really belongs today to the universe group the pipeline chose: the universe company must be the ultimate or controlling parent. Joint ventures without a controlling owner, minority stakes and former parents count as wrong.

- Gold file: `evals/gold/entity_matches.csv` (60 rows, one verdict and at least one evidence URL per row).
- Sample: `evals/gold/entity_matches_sample.csv`, a stratified random sample of 60 automatic links, seed 20261116: 30 `ch_psc_chain`, 10 `brand_prefix`, 7 `wikidata_company_number`, 7 `wikidata_subsidiary_name`, 6 `exact_name`.
- The pipeline was tightened after the sample was drawn. 58 of the 60 sampled links are still in `data/processed/uk_entity_group_map.parquet` (2,897 links). The two that are gone (01342230 and 00293529, both Eaton, both `ch_psc_chain`) were correct links. Column `still_in_current_map` records this.

### Method

1. Companies House public register, "persons with significant control" page of each of the 60 entities, fetched once each through the project's rate-limited client. `robots.txt` on that host returns HTTP 404, so no crawl restriction is published. Only corporate controllers were parsed; entries about individuals were ignored and not recorded.
2. A second source where the register alone could not settle the question: the group's own press release or annual accounts, a government registry, or Wikipedia as a secondary source.
3. Universe lookups in `data/processed/universe.parquet` to find the right group when the automatic one was wrong.

### Limits of this check

- For `ch_psc_chain` links, the Companies House register is the same underlying source the pipeline used. Those checks mainly verify the chain walk and the name match, not the ownership itself.
- Only the first hop of each chain was re-read on the live register. For 10 of the 30 `ch_psc_chain` rows the first hop is already the group's top company. For the other 20 the remaining hops are taken from the pipeline's own bulk-data chain and were not re-walked.
- 20 of 60 rows have a second, independent source (4 of the 30 `ch_psc_chain` rows, 16 of the other 30). 16 of those 20 rest on Wikipedia only; the other 4 use company accounts, a company press release, a trade press report or a government registry. The gold file has a `second_source` column.
- No row was marked unverifiable, but a few "correct" verdicts lean on general knowledge for one link in the chain (for example that ANC Holdings is a FedEx company, or that Interpublic now sits under Omnicom). The note column says so in each case.
- Precision is not recall. This sample says nothing about UK entities that should have been linked to a group and were not.
- The sample is stratified, so the overall sample figure overweights the small methods. See the weighted estimate below.
- Small strata: 6 to 10 rows per non-chain method. The per-method figures are indicative, not precise.

### Results

| Scope | Correct | Incorrect | Unverifiable | Precision |
|---|---|---|---|---|
| All 60 sampled links | 50 | 10 | 0 | 0.833 |
| 58 links still in the current map | 48 | 10 | 0 | 0.828 |

Weighted by the method mix of the current map (2,644 of 2,897 links are `ch_psc_chain`), the estimated precision of the map is about 0.91. That figure is driven by 26 correct out of 28 chain rows, so its uncertainty is wide (roughly 0.77 to 0.98 for the chain stratum).

#### By match method

| Method | Links in current map | Sampled | Correct | Precision (all sampled) | Precision (still in map) |
|---|---|---|---|---|---|
| `ch_psc_chain` | 2,644 | 30 | 28 | 0.933 | 26/28 = 0.929 |
| `brand_prefix` | 90 | 10 | 7 | 0.700 | 7/10 = 0.700 |
| `wikidata_company_number` | 70 | 7 | 5 | 0.714 | 5/7 = 0.714 |
| `wikidata_subsidiary_name` | 47 | 7 | 4 | 0.571 | 4/7 = 0.571 |
| `exact_name` | 46 | 6 | 6 | 1.000 | 6/6 = 1.000 |

#### By confidence level

| match_confidence | Sampled | Correct | Precision (all sampled) | Precision (still in map) |
|---|---|---|---|---|
| 0.95 | 15 | 14 | 0.933 | 13/14 = 0.929 |
| 0.90 | 28 | 25 | 0.893 | 24/27 = 0.889 |
| 0.85 | 7 | 4 | 0.571 | 4/7 = 0.571 |
| 0.75 | 10 | 7 | 0.700 | 7/10 = 0.700 |

The confidence values do not separate good links from bad ones well: the 0.95 band contains a wrong link and the 0.90 band three.

#### Incorrect links (all 10 are still in the current map)

| Company number | UK entity | Auto group | Method | Why it is wrong | Correct group |
|---|---|---|---|---|---|
| 04221944 | Punch Taverns (Services) Limited | Kohlberg Kravis Roberts | `ch_psc_chain` | Punch Pubs Group FY25 accounts name CF Cooper Holdings LP as ultimate parent; Wikipedia names Fortress Investment Group as owner since 2021. No source supports KKR. The chain walk above Punch Pubs & Co Group Limited (Argenta Holdco, Argenta Midco 2) looks wrong. | none in universe |
| 02214224 | Mitsubishi Corporation International (Europe) plc | Mitsubishi | `ch_psc_chain` | The owner is Mitsubishi Corporation. The universe record `mitsubishi-q183275` is the Mitsubishi group of companies, a set of formally independent firms with no controlling parent. Borderline, see below. | none in universe |
| 01630491 | Mitsubishi HC Capital UK plc | Mitsubishi | `brand_prefix` | Owner is Mitsubishi HC Capital Inc, a separately listed company. | none in universe |
| 02282265 | Mitsubishi Heavy Industries EMEA, Ltd. | Mitsubishi | `brand_prefix` | Owner is Mitsubishi Heavy Industries, Ltd., a separately listed company. | none in universe |
| 01878835 | Automobile Association Developments Limited | USAA | `brand_prefix` | UK roadside company The AA, owned by a TowerBrook and Warburg Pincus consortium. The key "automobile association" hit an alias of an unrelated US insurer. | none in universe |
| SC010975 | Dobbies Garden Centres Limited | Tesco | `wikidata_company_number` | Tesco sold Dobbies in June 2016. The register shows a different owner since July 2016. | `ares-management-corp-cik1176948` (Wikipedia only) |
| 00787446 | Mercedes-Benz Grand Prix Ltd | Ineos | `wikidata_company_number` | Ineos holds one third (register: 25 to 50%), as does Mercedes-Benz. Minority stake, no single parent. | none |
| 07934306 | Govia Thameslink Railway Limited | SNCF | `wikidata_subsidiary_name` | Govia is 65% Go-Ahead and 35% Keolis. SNCF only owns most of the minority partner. | none in universe |
| 02182098 | Merlin Entertainments (Sea Life) Limited | Blackstone Inc. | `wikidata_subsidiary_name` | Merlin is held by a consortium (Kirkbi, Blackstone, CPP Investments). Blackstone does not control it. | none |
| 03904624 | SEFE Energy Limited | Gazprom | `wikidata_subsidiary_name` | Former Gazprom business, now under SEFE, which is owned by the German state. The pipeline's own chain ends at the German federal ministry. | none in universe |

#### Judgement calls

Four verdicts could reasonably go the other way. Depending on how they are counted, precision on all 60 rows ranges from 47/60 = 0.783 to 51/60 = 0.850. No reading reaches 0.95.

- 02214224 Mitsubishi Corporation International (Europe): counted incorrect. It becomes correct if the universe record is redefined as Mitsubishi Corporation.
- OC303525 PricewaterhouseCoopers LLP: counted correct. It is a member firm of a network of separate legal entities, not an owned subsidiary.
- 03007940 West Coast Trains Limited: counted correct. Virgin held 51% of a joint venture with Stagecoach (49%), and the franchise ended in December 2019.
- 11116433 Hornsea 1 PSC Limited: counted correct on the register's control statement. The wind farm as an asset is co-owned, with Ørsted at 37.55%.

### Problems found beyond single rows

1. **Wikidata links are stale.** 5 of 14 Wikidata-based links are wrong, mostly former parents (Tesco and Dobbies, Gazprom and SEFE) or consortium members listed as owners. In 4 of those 5 cases the pipeline already held a Companies House chain that contradicted the Wikidata link and did not use it.
2. **The universe record "Mitsubishi" is a group of independent companies, not a company.** It carries a Wikidata revenue of USD 533bn and absorbs subsidiaries of at least three separate listed companies. All its UK links are suspect.
3. **Brand keys built from aliases are unsafe.** "automobile association" (USAA alias) matched The AA. The key "operative" for Co-operative Group is also risky, although the sampled row happened to be right.
4. **Private equity and consortium chains.** Chains ending at an investment firm (KKR, Blackstone, Ares) need care: the Punch link to KKR is contradicted by the company's own accounts.
5. **Entity names in the sample are out of date** for four entities that have since been renamed (for example Engie Fabricom UK is now Equans Fabricom UK). This does not affect the links.

### Recommendation

To get to 0.95 or above:

1. When a Companies House chain exists and ends somewhere other than the Wikidata group, let the chain win and send the link to `data/interim/review_queue.csv`. This alone would have removed 4 of the 10 errors (Dobbies, Govia Thameslink, Merlin, SEFE). Also require a controlling holding (more than 50%) at every hop: the Mercedes-Benz Grand Prix register entry shows Ineos at 25 to 50% only.
2. Drop `wikidata_subsidiary_name` links (47) unless a chain or the entity name confirms them. At 4/7 the method is not usable alone.
3. Keep `wikidata_company_number` (70 links) only where no chain contradicts it.
4. Restrict `brand_prefix` (90 links): build keys from the group's primary name only, never from aliases, block generic keys ("automobile association", "operative"), and require that the chain's top company contains the same brand.
5. Fix or remove the `mitsubishi-q183275` universe record, then rerun its links.
6. For `ch_psc_chain`, review chains that end at an asset manager or private equity firm by hand before they enter the final data. Do not treat 0.90 and 0.95 as meaningfully different until the bands are recalibrated.
7. Redraw a fresh sample after the changes and rerun this check. With about 250 links in the four small methods, checking all of them by hand is feasible and would remove most of the uncertainty. The chain stratum needs a larger sample (60 or more) and a live re-walk of the upper hops to support a 0.95 claim.

Until then, do not state a precision of 0.95 anywhere. The honest figure is 0.83 on the sample, about 0.91 weighted to the map.
