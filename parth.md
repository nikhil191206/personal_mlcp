# parth.md — Evidence, documentation, demo material

**Person:** Parth. **Read `parent.md` first**, fully. This file is your task spec and the prompt kit for your AI.

## How to use this file with your AI

Give your AI, in this order: (1) all of `parent.md`, (2) all of this file, (3) the kickoff prompt below. Your work is documents and checks, so demand this output format: one Markdown file per answer under a heading with its exact repo path, complete (no "rest unchanged"), in plain English a student team and a client can read, with no invented facts. Anything the AI cannot know (numbers from a run, source statuses, what a website says) must be left as a clearly marked `TODO(<who gives it>)` and filled in only from real data you or your teammates provide. Ask the AI to list its assumptions at the end.

### Kickoff prompt (paste as-is)

> You are helping me prepare the documentation and demo material for a student proof of concept: a scraping pipeline that collects public news about industrial compressor technology from approved USA sources and writes JSON to Databricks, for the client Atlas Copco. I have pasted the master brief (`parent.md`) and my task file. Write the Markdown files described in my task file, each under a heading with its exact repo path and complete. Do not invent facts, numbers, quotes or source statuses: where something comes from a run or from another teammate, put a visible `TODO(owner)` placeholder. Keep the language plain and short. Never include the Databricks token or any secret. List your assumptions at the end. If something is ambiguous, ask me.

---

## Your files

| File | What | Deadline |
|---|---|---|
| `docs/questions_for_atlas_copco.md` | questions to ask the client on Friday | Thu 18:00 |
| `docs/glossary.md` | plain-English terms for the team and the client | Thu 18:00 |
| `docs/keyword_suggestions.md` | extra compressor-related keywords and US locations to consider | Thu 21:00 |
| `docs/demo_note.md` | one-page demo note | template Thu 23:30, filled Fri 08:30 |
| `docs/check_results.md` | hand-check of 10 output items | Fri 08:30 |
| Volume screenshot | screenshot of the Databricks Volume for Atlas Copco | Fri 08:30 |

## Task P0 — Setup (first)

Follow `parent.md` section 12 (clone, venv, `.env`, your own token). `python -m atlas.storage_check` must print PASS with `ATLAS_PATH_PREFIX=dev/parth`. You need the setup to open the Volume and to run the pipeline for checking.

## Task P1 — `docs/questions_for_atlas_copco.md`

Start from these seven questions and tighten the wording. For each, add one line "Why we ask" and one line "What we will do with the answer". Keep to one page.

1. Please approve or change the 5 proposed sources. Which sources do you trust, and which should we avoid?
2. Can you give us a Databricks or Azure workspace so the data stays in your environment?
3. What should the summary report look like? Do you have a template?
4. Is there a narrower compressor topic you want first?
5. Is the weekly frequency right?
6. Who in your Legal team reviews the source list?
7. Is it fine for the AI step to use a hosted model, or must it be self-hosted?

Add at most three more questions that follow from `parent.md` (for example: how they want "fact" versus "claim" shown; whether "industrial" should be a required filter keyword; whether the 12-month recency window is right). Do not add more than 10 in total.

## Task P2 — `docs/glossary.md`

Start from `parent.md` section 19. Expand each term to a plain-English sentence or two, and add compressor terms a non-engineer would not know (rotary screw, centrifugal, reciprocating, oil-free, air end, CFM, PSI, bar, kW, VSD, air dryer, receiver, "compressor technique" as Atlas Copco's business area). Add pipeline terms (robots.txt, RSS, fingerprint, fact vs claim, evidence record, filter, register). Alphabetical order. Every definition must be something you can explain out loud.

## Task P3 — `docs/keyword_suggestions.md`

Suggest additions to the three lists in `config/keywords.yaml` (`compressor`, `industrial`, `us_locations`). Use this format so they can be merged quickly:

```markdown
## compressor
- term — why it matters (one phrase)
## industrial
- term — why
## us_locations
- term — why
## terms that might cause false matches
- term — why it is risky (for example a word that also means something else)
```

Aim for useful, specific terms (equipment types, drive types, treatment equipment, efficiency/regulation terms, major US industrial states and cities where compressor makers are based). Do not edit `config/keywords.yaml` yourself; Nikhil merges what he accepts.

## Task P4 — `docs/demo_note.md` (one page)

Template first (Thu 23:30), then fill with real data on Friday morning. Sections:

1. **What we built** — 3 sentences, plain language.
2. **How it works** — Input → Engine → Output in one short paragraph, plus the fact that nothing is stored locally.
3. **The 5 sources we propose, and why** — a table: name, type, how accessed (RSS/HTML), robots status, terms status. Source: `docs/source_vetting.md` from Ragini. Add the line: "These 5 are our proposed list; the approved list needs your sign-off, and your Legal team should review it before go-live."
4. **Sources we found blocked or excluded, and why** — from the vetting document.
5. **What the filter kept and dropped** — numbers from the run summary (collected, duplicates dropped, passed, dropped) and two or three example reasons. Source: the run summary text from Nikhil and the `clean/` folder files in Databricks.
6. **What we checked by hand** — result of the 10-item check (`docs/check_results.md`).
7. **Open questions for you** — pointer to `docs/questions_for_atlas_copco.md`.
8. **What comes next** — report, review page, AI summary, scheduling, other regions (from `parent.md` section 3).

Any number or status you do not have yet stays `TODO(<who>)`. Only real, checked values go in the final version.

## Task P5 — `docs/check_results.md` (hand-check of 10 items)

After the dev run is available (Fri 07:30 onward; Nikhil tells you which prefix and run id), open the output in Databricks: Catalog → atlas_poc → default → data → `<prefix>` → `output` → `poc_<run_id>.json`. Pick **10 items** from at least 3 different sources. For each item, open its `source_url` in a browser and check:

| Check | How |
|---|---|
| Title matches the page | compare headline |
| Date matches the page | compare published date; if the item says `null`, is the date really missing on the page? |
| Label is right | fact or claim, by the rule in `parent.md` section 19 |
| Company is right | the company the page is about |
| Technology is plausible | matches what the page says, or `null` if not stated |
| Key facts are true | each fact appears on the page, and is short |
| No personal data | no names, emails or phone numbers in the item |
| Filter result makes sense | would a person agree it is compressor-related, US, recent? |

Record in this format:

```markdown
| # | item id | source | URL | title ok | date ok | label ok | company ok | technology ok | facts ok | no PII | filter ok | notes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
```

Use `yes` / `no` / `n/a`. For every `no`, write one line saying what was wrong, and send those lines to the owner: extraction problems (title, date, label, company, technology, facts, PII) go to Sachi; filter problems go to Nikhil; wrong or blocked sources go to Ragini. Finish with a short summary: how many of 10 were fully correct, and the main error types. Never guess: if you cannot verify an item, write `n/a` and why.

Also verify two global facts and record them: (1) the six folders exist and are filled in the Volume after the final demo run, (2) no data files are on your laptop (`git status` shows no data; look through the project folder).

## Task P6 — Volume screenshot

After Nikhil's final demo run (Fri 08:30), take a screenshot of the Databricks Volume showing the six folders (`source_register`, `raw`, `clean`, `facts`, `output`, `logs`) and, if possible, one screenshot of the open `output/poc_<run_id>.json`. Save the screenshots **outside the git repo** (they are for sending to Atlas Copco, not for committing). Make sure the screenshot does not show your token or any personal details.

## Acceptance criteria (yours)

- [ ] `docs/questions_for_atlas_copco.md`, `docs/glossary.md`, `docs/keyword_suggestions.md`, `docs/demo_note.md` and `docs/check_results.md` are pushed to `main`.
- [ ] The demo note has no `TODO` left, and every number in it matches the real run.
- [ ] 10 items were checked against their live pages from at least 3 sources, and each error was reported to its owner.
- [ ] The Volume screenshots exist and show nothing secret.
- [ ] Nothing in your files contains a token, an invented quote, or an invented number.

## Do not

- Do not edit code or config files; send suggestions to the owner.
- Do not invent source statuses, quotes or numbers; use real ones or leave a `TODO`.
- Do not commit screenshots, data files, or anything with the token.
- Do not copy articles or long quotes from websites into your notes.
