# Hand-check of 10 output items

**Status: not started. This file is a template.** It can only be completed after a real pipeline run exists, because every row has to be checked against the live source page. No row below has been checked, and none may be filled in from memory or guessed.

## How to do it

1. Get the prefix and `run_id` from Nikhil. Open Databricks: Catalog, `atlas_poc`, `default`, `data`, then `<prefix>`, `output`, `poc_<run_id>.json`.
2. Pick 10 items from at least 3 different sources.
3. For each, open its `source_url` in a browser and answer yes / no / n/a for every column:

| Column | What to compare |
|---|---|
| title ok | the item's `title` against the page headline |
| date ok | `published_at` against the page date (if the item says `null`, is the date really missing on the page?) |
| label ok | `fact` or `claim` against the rule: claim = a company says it about itself; fact = neutral or official source, or a reporter reporting an event |
| company ok | the company the page is about |
| technology ok | matches what the page says, or `null` when the page does not say |
| facts ok | each `key_facts` statement appears on the page and is short |
| no PII | no names, emails or phone numbers anywhere in the item |
| filter ok | would a person agree it is compressor-related, in North America, and recent? |

4. For every `no`, write one line in the notes column. Send extraction problems (title, date, label, company, technology, facts, PII) to Sachi; filter problems to Nikhil; source or blocking problems to Ragini.
5. If an item cannot be verified, write `n/a` and the reason. Never guess.

## Run being checked

- Prefix: TODO(Nikhil)
- run_id: TODO(Nikhil)
- Checked by: TODO(Parth)
- Checked on: TODO(Parth)

## Results

| # | item id | source | URL | title ok | date ok | label ok | company ok | technology ok | facts ok | no PII | filter ok | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | TODO | TODO | TODO | | | | | | | | | |
| 2 | TODO | TODO | TODO | | | | | | | | | |
| 3 | TODO | TODO | TODO | | | | | | | | | |
| 4 | TODO | TODO | TODO | | | | | | | | | |
| 5 | TODO | TODO | TODO | | | | | | | | | |
| 6 | TODO | TODO | TODO | | | | | | | | | |
| 7 | TODO | TODO | TODO | | | | | | | | | |
| 8 | TODO | TODO | TODO | | | | | | | | | |
| 9 | TODO | TODO | TODO | | | | | | | | | |
| 10 | TODO | TODO | TODO | | | | | | | | | |

## Summary

- Items fully correct: TODO of 10
- Main error types: TODO
- Errors sent to owners: TODO (who, what)

## Global checks after the final demo run

| Check | Result |
|---|---|
| The six folders (`source_register`, `raw`, `clean`, `facts`, `output`, `logs`) exist and are filled in the Volume | TODO yes / no |
| No data files on the laptop (`git status` shows no data; project folder looked through) | TODO yes / no |
| Volume screenshots saved outside the repo, with no token or personal details visible | TODO yes / no |
