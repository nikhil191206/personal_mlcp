# Decisions log

Questions asked, answers received, and spec deviations. Newest last.

| Date | Question / issue | Answer / decision |
|---|---|---|
| 2026-10-29 | Working rule | Serious project: no workarounds or fallback modes without explicit user approval. |
| 2026-10-29 | Databricks workspace, schema `atlas_poc`, volume `data`, token | Already set up by the user; user fills `.env`. |
| 2026-10-29 | Volume location | Differs from spec: catalog `atlas_poc`, schema `default`, volume `data` (so root is `/Volumes/atlas_poc/default/data`). |
| 2026-10-29 | VERIFY: Free Edition allows personal access tokens and the Files API? | Yes. `storage_check` PASS: write, read back, list all work from memory with a token; no local files created. |
| 2026-10-29 | Contact email for the User-Agent | `industrymlcp@gmail.com` |
| 2026-10-29 | Which 5 sources run on Friday | airbestpractices_news, quincy_compressor_blog, sullair_america_news, pumps_systems_news, doe_newsroom (team to confirm). Replaced after live runs: atlas_copco_usa_news (the client's own site adds nothing to a market study) and kaeser_usa_blog (posts carry no date, so none can pass "recent"). Vetted but not in the register: atlas_copco_usa_news, kaeser_usa_blog, atlas_copco_group_press, elgi_usa. |
| 2026-10-29 | Sources that refuse us without a ban (403/429) | Recorded `vetting_status: unreachable`, approval `status: needs_permission`; not retried or bypassed (Plant Engineering, Ingersoll Rand, Business Wire). |
| 2026-10-29 | Kaeser terms | No terms-of-use page found; recorded `terms_status: unknown` and flagged for Atlas Copco Legal. |
| 2026-10-29 | Dates found by trafilatura's extensive search | A date of exactly 1 January found only by that search is treated as no date (a bare "© 2026" footer was read as 2026-01-01). Real datelines in the text are still used. |
| 2026-10-29 | `fact` label for trade news | Narrowed to acquires/acquired/files/filed/completes/completed/appoints/fined/recall/regulation. "standard", "rule", "opens", "announces plans" removed: trade sites mostly republish company press releases, which are claims. |
| 2026-10-29 | Company for non-competitor sources | Known companies (`config/aliases.yaml`) first; spaCy ORG fallback only if the same name appears at least twice (headline repeats not counted); otherwise `null`. |
| 2026-10-29 | Personal-data scrub | Presidio allow-list of known company names and US place names, so they are not replaced by `<PERSON>`. The small model still over-removes some other words; this errs on the safe side. |
| 2026-10-29 | Team work split | Four people, file-level ownership; contracts fixed in `parent.md` and `atlas/models.py`. See `wd.md`. |
| 2026-10-29 | Dev vs demo storage | `ATLAS_PATH_PREFIX=dev/<name>` for development; only the final demo run uses an empty prefix. |
| 2026-10-29 | Filter inputs | Text is dropped after extraction, so extract computes `matched_keywords`, `mentions_us_location`, `industrial_hint` on `Item`; filter uses those and the title. |
| 2026-10-29 | Is "industrial" a required keyword? | No. Recorded as the `industrial_hint` flag only. |
| 2026-10-29 | Personal-data removal tool | Presidio + spaCy `en_core_web_sm`. |
| 2026-10-29 | Spec gap: gate vs `proposed` status | Spec says the gate skips non-approved sources, but all sources stay `proposed` until Atlas Copco signs off. Gate admits `proposed` and `approved`; rejects `blocked`, `needs_permission`, `unreachable`. |
| 2026-10-29 | Spec gap: two status lists | `sources.yaml` gets `vetting_status` (working / blocked / needs_permission / unreachable) separate from approval `status` (proposed / approved). |
