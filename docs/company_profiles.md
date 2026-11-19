# Company profiles, validation and company reports (phase 3)

How to use tasks 2, 3, 6, 7, 8 and 10, and the rules behind them.

## Commands

```bash
# 1. A normal run now also validates every item and writes the company index (no website reading)
python -m atlas.run --max-items 5

# 2. Company profiles: read each company's own website for contacts, logo and images, then build reports
python -m atlas.companies --fetch-profiles --reports both

# Only one company, an older run, or only PDFs
python -m atlas.companies --run-id 20261115T204628Z --only "Kaeser Compressors" --reports pdf
```

On the website, the new **Companies** page lists every company in the selected run with its items, how many
are confirmed and why, its contacts (after `--fetch-profiles`) and PDF / PowerPoint buttons for its report.

## What gets written to the Volume

| Path | What |
|---|---|
| `output/poc_<run>.json` | as before; each item now has `validation`, `company_method`, `company_confidence`, `headings`, `summary`, `image_url` |
| `companies/<run>/index.json` | one profile per company, the unattributed item ids, and the validation rules |
| `companies/<run>/<company_id>.json` | one company's profile and its items |
| `companies/<run>/<company_id>/logo.<ext>` | the company's logo (only after `--fetch-profiles`) |
| `reports/companies/<run>/<company_id>.pdf` / `.pptx` | the company report |

## Task 2. Company discovery

When the page is not on a competitor's own newsroom and no known company (config/aliases.yaml) is named,
`atlas/company.py` looks for: a stock ticker ("Acme Corp (NYSE: ACME)"), the press-release "About Acme Corp"
section, a schema.org Organization the page is about (never the publisher), the headline subject
("Acme Corp launches ..."), and an organisation spaCy finds twice. Two rules agreeing gives high
confidence; a single headline or spaCy hit gives low confidence. Two different companies with equal support
gives no company. Each item records the rule (`company_method`), the confidence and the phrase that named it.

## Task 3. Content extraction

- Main text: Trafilatura in precision mode first; if that leaves under 200 characters, a second recall pass
  that also keeps tables (spec sheets and award lists were losing their facts).
- Title: page metadata, then og:title, then the first h1, then the feed title.
- Date: page metadata, then schema.org `datePublished`, then the dateline; still never the fetch date.
- New fields: up to 5 page headings (h1 to h3, navigation and footers skipped), the page's own meta
  description as `summary` (300 characters), and the og:image link. All scrubbed of personal data.

## Task 6. Company-wise classification

`atlas/companies.py` groups items by company after cleaning (so "Kaeser" and "Kaeser Compressors" are one
company), with counts by type of news, technology and region, the products named, the date range, the
sources and the stories. Items without a company are listed separately as unattributed, never guessed.

## Task 7. Validation rules

An item is **Confirmed** when at least one holds and nothing blocks it:

- **C1 corroborated:** the same story was reported by 2 or more independent websites.
- **C2 authoritative:** a government source, or a trade-news report of a hard event (acquisition, filing,
  appointment, fine, recall), with the article's own date.
- **C3 reviewed:** a team member marked the fact Important on the Facts page.

Blocked (always Not confirmed): the company was found only by a weak rule, or the team marked it Not important.
Every item keeps `evidence_urls`: its own link and the links of the other items in its story.

A **contact** is Confirmed when it was read from the company's own website in schema.org data, or seen on
2 or more of its pages.

## Task 8. Contacts and images

Read only from the company's own website (config/companies.yaml, plus every competitor in sources.yaml), the
homepage and up to 3 contact / about / company / locations pages, through the Compliance Gate. A website the
register refuses (for example Ingersoll Rand) is not read, and the profile says why.

- Emails: only role mailboxes on the company's own domain (info@, sales@, service@ ...). Addresses that look
  personal are counted and dropped, never stored. The company report refuses to build if one gets through.
- Phones: tel: links, schema.org data, or text labelled phone / tel / call / toll-free; fax numbers skipped.
- Addresses: schema.org PostalAddress or an `<address>` element.
- Logo: schema.org logo, an image marked as the logo, or the touch icon. It is the only image copied (to the
  Volume, for identification in the report). Other images are kept as links.

## Task 10. Company reports

One page per company, as a PDF (one landscape A4 page) and/or PowerPoint (one 16:9 slide), in Atlas Copco's
market-intelligence format and nothing else: the company name as the title, the logo top right (a dashed
LOGO box when there is none), a line under the title with the report date and the company contact (role
emails and main phone numbers), and six labelled boxes:

| Left column | Right column |
|---|---|
| Business Description and Ownership structure: office address, ownership / partnership / investment / leadership news | Products, markets and finances: products named, technologies, regions, figures stated in the news |
| Technology/ Product/ Service Description: technology facts and the pages' own summaries | Technology assessment by Atlas Copco: the evidence (items, confirmed, how, types of news, dates) |
| Value for Atlas Copco: the fixed "why it matters" sentence per type of news | Links and attachments: website, top news links, patents |

Nothing is invented. Fields the sources do not give (founded, employees, revenue, unit cost, capacity,
customers, patents, and the contact when none was found) say "not stated in the collected sources (to
complete)" so the analyst can fill them in on the editable slide. Facts not yet confirmed carry a `*`, and
every fact has a "source" link. The two judgement boxes are marked "To complete by Atlas Copco". Each box
keeps only as many lines as fit (`atlas/report/company_sheet.py`, `CAPACITY`), and the PDF builder refuses
to write a report that runs onto a second page.

The report date is the run's date (from the run id). The full evidence (every item with its validation,
contacts with status, image links, sources) is not in the report; it stays in
`companies/<run_id>/<company_id>.json` and on the Companies page. The slide's speaker notes list the source
links.
