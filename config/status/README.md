# Account status (the feedback loop)

`config/status/accounts_status.csv` is the one file the queue respects. Append a row when something happens. The newest row per account wins.

| Column | Required | Meaning |
|---|---|---|
| `company_id` or `company` | one of them | The account (name is resolved like everywhere else) |
| `status` | yes | `contacted`, `meeting`, `won`, `lost`, `not_a_fit` |
| `reason` | for `lost` and `not_a_fit` | Why, in a few words. This is the part that improves the model |
| `date` | yes | YYYY-MM-DD |
| `play` | no | dinner_invite, cold_email, investor_intro, warm_via_supplier |

What the queue does with it: `won`, `lost` and `not_a_fit` accounts leave the queue. `contacted` accounts are held back for 21 days, then return as a follow-up. `meeting` accounts stay visible with the play "prepare the meeting".

`make feedback` (or `.venv/bin/python -m chase.gtm.feedback`) reports which score components separate meetings from rejections once there are at least 20 outcomes. `demo_accounts_status.csv` in this folder is SYNTHETIC and only used with `--demo`.
