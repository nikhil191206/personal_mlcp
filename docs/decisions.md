# Decisions log

Questions asked, answers received, and spec deviations. Newest last.

| Date | Question / issue | Answer / decision |
|---|---|---|
| 2026-10-29 | Working rule | Serious project: no workarounds or fallback modes without explicit user approval. |
| 2026-10-29 | Databricks workspace, schema `atlas_poc`, volume `data`, token | Already set up by the user; user fills `.env`. |
| 2026-10-29 | Volume location | Differs from spec: catalog `atlas_poc`, schema `default`, volume `data` (so root is `/Volumes/atlas_poc/default/data`). |
| 2026-10-29 | Is "industrial" a required keyword? | No. Recorded as the `industrial_hint` flag only. |
| 2026-10-29 | Personal-data removal tool | Presidio + spaCy `en_core_web_sm`. |
| 2026-10-29 | Spec gap: gate vs `proposed` status | Spec says the gate skips non-approved sources, but all sources stay `proposed` until Atlas Copco signs off. Gate admits `proposed` and `approved`; rejects `blocked`, `needs_permission`, `unreachable`. |
| 2026-10-29 | Spec gap: two status lists | `sources.yaml` gets `vetting_status` (working / blocked / needs_permission / unreachable) separate from approval `status` (proposed / approved). |
