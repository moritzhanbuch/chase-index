# Site check

Run: 2026-11-17 22:28 UTC. Method: Playwright (Chromium, headless) against a local static server on 127.0.0.1 serving `site/dist`. Nothing was deployed.

## Result

- Page loads: 24 of 24 pass (no console errors, no failed requests, no external requests, no horizontal overflow, h1 and disclaimer present).
- Console errors: 0. Failed requests: 0. Requests to external hosts: 0.
- Horizontal overflow at 375 px: 0 pages. Lookup results at 375 px overflow: no.
- Supplier lookup by name: 10 of 10 show the same average days to pay as the data. By company number: 10 of 10.
- Searched entity is the first result when searching by name: 10 of 10 (others share a name prefix with a shorter-named entity).
- Lookup index is lazy-loaded (not requested before the first keystroke): yes.
- Home table: country filter narrows 502 rows to 84 for GB, default order is alphabetical, sorting by days to pay works, show-all works: pass.
- Build: 812 pages, 10.7 MB, lookup index 955 kB.

## Pages

| Page | Path | Viewport | Console errors | Failed requests | External requests | Overflow | Result | Screenshot |
|---|---|---|---|---|---|---|---|---|
| home | `index.html` | desktop 1280px light | 0 | 0 | 0 | no | pass | `site_screenshots/home_desktop.png` |
| company | `company/puig-q3410623.html` | desktop 1280px light | 0 | 0 | 0 | no | pass | `site_screenshots/company_desktop.png` |
| lookup | `lookup.html` | desktop 1280px light | 0 | 0 | 0 | no | pass | `site_screenshots/lookup_desktop.png` |
| spain | `spain.html` | desktop 1280px light | 0 | 0 | 0 | no | pass | `site_screenshots/spain_desktop.png` |
| methodology | `methodology.html` | desktop 1280px light | 0 | 0 | 0 | no | pass | `site_screenshots/methodology_desktop.png` |
| faq | `faq.html` | desktop 1280px light | 0 | 0 | 0 | no | pass | `site_screenshots/faq_desktop.png` |
| about | `about.html` | desktop 1280px light | 0 | 0 | 0 | no | pass | `site_screenshots/about_desktop.png` |
| data | `data.html` | desktop 1280px light | 0 | 0 | 0 | no | pass | `site_screenshots/data_desktop.png` |
| data-dictionary | `data-dictionary.html` | desktop 1280px light | 0 | 0 | 0 | no | pass | `site_screenshots/data-dictionary_desktop.png` |
| limitations | `limitations.html` | desktop 1280px light | 0 | 0 | 0 | no | pass | `site_screenshots/limitations_desktop.png` |
| corrections | `corrections.html` | desktop 1280px light | 0 | 0 | 0 | no | pass | `site_screenshots/corrections_desktop.png` |
| home | `index.html` | desktop 1280px dark | 0 | 0 | 0 | no | pass | `site_screenshots/home_desktop_dark.png` |
| company | `company/puig-q3410623.html` | desktop 1280px dark | 0 | 0 | 0 | no | pass | `site_screenshots/company_desktop_dark.png` |
| home | `index.html` | mobile 375px light | 0 | 0 | 0 | no | pass | `site_screenshots/home_mobile.png` |
| company | `company/puig-q3410623.html` | mobile 375px light | 0 | 0 | 0 | no | pass | `site_screenshots/company_mobile.png` |
| lookup | `lookup.html` | mobile 375px light | 0 | 0 | 0 | no | pass | `site_screenshots/lookup_mobile.png` |
| spain | `spain.html` | mobile 375px light | 0 | 0 | 0 | no | pass | `site_screenshots/spain_mobile.png` |
| methodology | `methodology.html` | mobile 375px light | 0 | 0 | 0 | no | pass | `site_screenshots/methodology_mobile.png` |
| faq | `faq.html` | mobile 375px light | 0 | 0 | 0 | no | pass | `site_screenshots/faq_mobile.png` |
| about | `about.html` | mobile 375px light | 0 | 0 | 0 | no | pass | `site_screenshots/about_mobile.png` |
| data | `data.html` | mobile 375px light | 0 | 0 | 0 | no | pass | `site_screenshots/data_mobile.png` |
| data-dictionary | `data-dictionary.html` | mobile 375px light | 0 | 0 | 0 | no | pass | `site_screenshots/data-dictionary_mobile.png` |
| limitations | `limitations.html` | mobile 375px light | 0 | 0 | 0 | no | pass | `site_screenshots/limitations_mobile.png` |
| corrections | `corrections.html` | mobile 375px light | 0 | 0 | 0 | no | pass | `site_screenshots/corrections_mobile.png` |

## Lookup test

10 entities sampled from `uk_entity_latest.parquet` (seed 20261116): 9 with a current report, 1 with an old report. Each is typed into the search box by name and by company number.

| Entity | Number | Query by | Days in data | Days shown | First result | Old report | Result |
|---|---|---|---|---|---|---|---|
| THOMPSON AND CAPPER LIMITED | 00235815 | name | 43 | 43 | yes | no | pass |
| THOMPSON AND CAPPER LIMITED | 00235815 | number | 43 | 43 | yes | no | pass |
| D.P.K. FOODS LTD. | SC198617 | name | 8 | 8 | yes | no | pass |
| D.P.K. FOODS LTD. | SC198617 | number | 8 | 8 | yes | no | pass |
| BLACKDOWN EDUCATION PARTNERSHIP | 07338835 | name | 12 | 12 | yes | no | pass |
| BLACKDOWN EDUCATION PARTNERSHIP | 07338835 | number | 12 | 12 | yes | no | pass |
| CAPITAL ARCHES GROUP LIMITED | 10139149 | name | 23 | 23 | yes | no | pass |
| CAPITAL ARCHES GROUP LIMITED | 10139149 | number | 23 | 23 | yes | no | pass |
| GREENCORE FOODS LIMITED | 07441672 | name | 28 | 28 | yes | no | pass |
| GREENCORE FOODS LIMITED | 07441672 | number | 28 | 28 | yes | no | pass |
| NORTHERN IRELAND ELECTRICITY NETWORKS LIMITED | NI026041 | name | 38 | 38 | yes | no | pass |
| NORTHERN IRELAND ELECTRICITY NETWORKS LIMITED | NI026041 | number | 38 | 38 | yes | no | pass |
| TOM MARTIN & COMPANY LIMITED | 00990667 | name | 35 | 35 | yes | no | pass |
| TOM MARTIN & COMPANY LIMITED | 00990667 | number | 35 | 35 | yes | no | pass |
| TENTERDEN SCHOOLS TRUST | 07736448 | name | 20 | 20 | yes | no | pass |
| TENTERDEN SCHOOLS TRUST | 07736448 | number | 20 | 20 | yes | no | pass |
| SUNDERLAND CARE AND SUPPORT LIMITED | 08681649 | name | 8 | 8 | yes | no | pass |
| SUNDERLAND CARE AND SUPPORT LIMITED | 08681649 | number | 8 | 8 | yes | no | pass |
| ARJOWIGGINS SOURCING LIMITED | 06824918 | name | 57 | 57 | yes | yes | pass |
| ARJOWIGGINS SOURCING LIMITED | 06824918 | number | 57 | 57 | yes | yes | pass |

## Failures and fixes

None in this run.
