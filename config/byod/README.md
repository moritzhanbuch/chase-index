# Bring your own data

Drop any of these files into `config/byod/` and re-run `make queue`. Each is optional. Nothing here leaves your machine: the files are read locally and `config/byod/*.csv` is gitignored. The folder `config/byod/demo/` holds a **SYNTHETIC** demo set (invented rows, real company names from the public index used only as join keys) so you can see the effect: `make queue DEMO=1`.

Account names are matched to the index with the same resolver the skill uses (company_id, exact name, alias, then a conservative prefix match). Rows that do not match are listed by `byod_status` (MCP) and in `outputs/queue/byod_unmatched.csv` after `make queue` (gitignored), and are never guessed.

## `network_suppliers.csv`: who is already on the network

| Column | Required | Meaning |
|---|---|---|
| `name` | yes | Legal or trading name of the network account |
| `account_type` | yes | `supplier` or `buyer` |
| `sector` | no | One of the index sectors (manufacturing, automotive, construction, retail, consumer_goods, energy, pharma, logistics, utilities, telecom, technology, services). Used for the peer flag |
| `country` | no | ISO-2 |
| `known_customers` | no | Pipe-separated buyer names this supplier invoices (you know this from the invoices on the network). This is what creates a **warm** flag |
| `since` | no | Date the account joined |

Effect: an index account named in a supplier's `known_customers` gets `warm_via_supplier` (strong, with the supplier names as the reason). An index account in the same sector and country as a `buyer` on the network gets `peer_on_network` (weak). An index account that is itself a `buyer` on the network is marked `already_customer` and leaves the queue.

## `crm_accounts.csv`: your current pipeline

| Column | Required | Meaning |
|---|---|---|
| `account_name` | yes | Account name as in your CRM |
| `stage` | yes | Free text; anything except `closed_lost` and `disqualified` marks the account as `in_pipeline` |
| `owner` | no | Who owns it |
| `last_touch` | no | Date of the last touch (YYYY-MM-DD) |

Effect: `in_pipeline` accounts stay in the queue but the suggested play becomes "brief the owner" and the row shows stage and owner. `closed_lost` and `disqualified` accounts are held back like a `lost` status.

## `dinner_attendees.csv`: who came, who was invited

| Column | Required | Meaning |
|---|---|---|
| `city` | yes | munich, paris, london, madrid, hamburg ... |
| `date` | yes | YYYY-MM-DD |
| `account_name` | yes | The company |
| `status` | yes | `invited`, `accepted`, `attended`, `declined` |

Effect: `attended` gives a `met_at_dinner` flag and the play becomes a follow-up; `invited` or `accepted` for an upcoming dinner removes the dinner-invite play (no double invites); `declined` suppresses dinner invites for that city.

## `investor_links.csv` (optional fourth slot)

| Column | Required | Meaning |
|---|---|---|
| `account_name` | yes | The target account |
| `investor` | yes | The investor who can introduce you |
| `relationship` | no | Free text (board seat, LP, portfolio customer) |

Effect: enables the "investor intro" play for that account. Without this file that play is never suggested, because the index has no public data on who knows whom.
