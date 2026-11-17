# About The Chase Index

I'm Moritz Hanbuch, a student at IE University in Madrid. I built this index unasked, with AI agents, as an application project for an agent-to-agent B2B payments startup.

## Why

Late payment is one of the oldest problems in business. The data to see it is public, but it is scattered and hard to use. UK companies file their payment reports per legal entity. Spanish companies put one number in the notes of a long annual report. I wanted one place where a supplier or a finance team can look a company up and get the figure, the period and the source.

## What it is

- A dataset of what large companies report about paying suppliers: {{ h.uk_current_n|int_c }} UK legal entities with a current statutory report, and {{ h.es_n }} IBEX 35 companies in Spain.
- A link from UK legal entities to {{ h.groups_uk_n|int_c }} parent groups, built from public ownership records. Links can be wrong or out of date, see the [limitations](limitations.html).
- A separate, clearly labelled balance-sheet proxy (computed DPO) for listed groups.
- A free [supplier lookup](lookup.html): how long does my customer take to pay?
- Open about its method. Read the [methodology](methodology.html) and the [limitations](limitations.html).

## What it is not

- Not an official publication. The official sources are linked on every figure, and they win when there is a difference.
- Not a judgement about any company. A long average can come from long agreed terms, from one unusual entity or from how a company counts. The figures are the companies' own.
- Not a statement about how a group pays worldwide. UK figures cover UK legal entities. Spanish figures cover Spanish entities.
- Not a product of any company. Nobody asked for it, paid for it or reviewed it.

## How it was built

AI agents did most of the work: they downloaded the official data, parsed it, matched entities to groups, read the Spanish annual reports twice with two independent methods, and checked each other's output. I set the rules, the checks and the standard: every number has a source, a period and a retrieval date, and nothing is made up. Where the pipeline could not get a value, the cell is empty.

## Which company pages exist

Every group with reported UK or Spanish data has a page. So do the {{ h.proxy_page_cap }} largest other groups by revenue that have a computed DPO on the clean basis (trade payables and cost of sales). That keeps the site small. The [CSV downloads](data.html) contain all rows.

## Contact and corrections

Found an error? See [corrections](corrections.html).

## Privacy

- This site sets no cookies and uses no tracking or analytics.
- The supplier lookup runs in your browser. What you type is not sent anywhere.
- The hosting provider keeps standard server logs (IP address, time, page requested), as every web server does.
- If you email a correction, your message and address are used only to handle that request.

## Imprint

Responsible for this site: Moritz Hanbuch

Address: {{ imprint_address }}

Email: `{{ contact }}`

{{ disclaimer }}
