# Download the data

Two CSV files, rebuilt from the official sources every time the site is built. They contain reported figures, the computed DPO proxy, periods and source links. Nothing else.

| File | Rows | What it is |
|---|---|---|
| [chase-index-uk-entities.csv](data/chase-index-uk-entities.csv) | {{ files.entities_rows|int_c }} | One row per UK legal entity with a usable statutory payment report: the latest report's figures, period, year-on-year change, a link to the official report and, where matched, the parent group. |
| [chase-index-groups.csv](data/chase-index-groups.csv) | {{ files.groups_rows|int_c }} | One row per large group with reported UK or Spanish data or a computed DPO proxy: group-level UK means, the Spanish statutory payment period, the proxy with its basis, and source links. |

Column definitions are in the [data dictionary](data-dictionary.html). A plain-text summary for machines is in [llms.txt](llms.txt).

## Licence and attribution

- **UK figures.** {{ ogl }} Source: Payment Practices and Performance Reporting service, Department for Business and Trade. The UK columns in these files are derived from that data and can be reused under the same [Open Government Licence v3.0](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).
- **Spanish figures and the DPO proxy.** These are facts and calculations derived from companies' published annual reports. The filings themselves are not copied here. Each row links to the filing.
- **The compilation.** The selection, cleaning and group links are published under [{{ licence_name }}]({{ licence_url }}). The UK figures remain public sector information under the Open Government Licence v3.0 and must keep that attribution. Group links are derived from Companies House public data (persons with significant control, corporate records only). Revenue and identifiers come from company filings and from Wikidata (CC0). Please cite "The Chase Index, Moritz Hanbuch" and keep the source links.
- **Companies House.** {{ ch_attribution }}.

## Read before you use it

- Reported and computed figures are different things. Columns that start with `uk_` or `es_` are reported. Columns that start with `computed_dpo_proxy` are calculated from balance sheets and are a proxy.
- UK group figures cover UK legal entities only, matched to the group. They are not a statement about the group's global payment behaviour.
- UK group figures are averages across matched UK entities, weighted by the invoice value each entity reports paying. The simple mean is published alongside, and `uk_days_aggregation` says which one applies.
- Spanish figures cover the group's Spanish entities as disclosed under Ley 15/2010.
- An empty cell means no figure. It never means zero.
- Data retrieved {{ data_date }}. The official source wins. See [corrections](corrections.html).

{{ disclaimer }}
