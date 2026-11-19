# Backend architecture and end-to-end workflow

This is the whole Market Scout backend after phase 3. The diagrams are Mermaid, so GitHub draws them; in VS Code
use a Mermaid preview extension.

## 1. Components

```mermaid
flowchart LR
    subgraph Config["config/ (in the repo)"]
        SRC[sources.yaml<br/>source register]
        KW[keywords.yaml<br/>technologies.yaml<br/>aliases.yaml<br/>products.yaml]
        CO[companies.yaml<br/>company websites]
        SEEDS[discovery_seeds.yaml]
        SET[scout_settings.yaml<br/>default settings]
    end

    subgraph Engine["atlas/ (Python)"]
        GATE[compliance.py<br/>Compliance Gate]
        DISC[scout/discover.py + vet.py<br/>source discovery]
        SEARCH[scout/search_provider.py<br/>Firecrawl search API, optional]
        COL[collect.py<br/>RSS / HTML collector]
        EXT[extract.py<br/>Trafilatura + Presidio/spaCy]
        COMP[company.py<br/>company discovery]
        CLEAN[clean.py<br/>dedupe, ISO dates, names]
        FILT[filter.py<br/>relevance filter]
        FB[scout/fallback.py<br/>switching for refused sources]
        STORY[scout/stories.py<br/>stories]
        VAL[validate.py<br/>Confirmed / Not confirmed]
        CMP[companies.py<br/>company-wise index]
        PROF[profile.py<br/>contacts, logo, images]
        REP[report/<br/>build, brief, onepager,<br/>company_report]
    end

    subgraph Volume["Databricks Volume"]
        V1[(source_register/ raw/ clean/ facts/)]
        V2[(output/poc_RUN.json<br/>logs/RUN.json)]
        V3[(companies/RUN/<br/>index.json, company.json, logos)]
        V4[(reports/ and reports/companies/RUN/)]
        V5[(settings/ scout/)]
    end

    subgraph UI["web/ (React + local API)"]
        API[api/server.py<br/>127.0.0.1:8765]
        SITE[React site<br/>127.0.0.1:5173]
    end

    WEB((Public websites))

    SRC --> GATE
    SEEDS --> DISC
    SEARCH --> DISC
    DISC --> GATE
    GATE --> COL
    COL <--> WEB
    PROF <--> WEB
    COL --> EXT
    KW --> EXT
    EXT --> COMP
    EXT --> CLEAN --> FILT --> FB --> STORY --> VAL --> CMP
    CO --> PROF
    GATE --> PROF
    PROF --> CMP
    CMP --> REP
    COL -. metadata only .-> V1
    FILT --> V1
    VAL --> V2
    CMP --> V3
    REP --> V4
    SET --> V5
    API <--> V2
    API <--> V3
    API <--> V4
    API <--> V5
    SITE <--> API
```

## 2. End-to-end workflow of one run

```mermaid
sequenceDiagram
    autonumber
    participant U as Team member
    participant UI as Website / CLI
    participant R as atlas.run
    participant G as Compliance Gate
    participant W as Public website
    participant X as Extract + clean + filter
    participant V as Validate + companies
    participant D as Databricks Volume

    U->>UI: change filters, or run python -m atlas.run
    UI->>R: start a run (saved settings)
    R->>D: load settings, candidates, fact decisions
    opt discovery on
        R->>G: seeds, outbound links, Firecrawl search results
        G->>W: robots.txt, homepage, terms page (3 s apart)
    end
    loop every source in the register (+ usable discovered ones)
        R->>G: check status, terms, robots.txt
        alt refused
            G-->>R: refusal with reason (logged, shown, never bypassed)
        else allowed
            G->>W: listing (RSS or HTML), then item pages
            W-->>R: pages, held in memory only
            R->>X: extract one record per page, scrub personal data
            X-->>R: items (no page text), cleaned and filtered
            R->>D: raw/, clean/, facts/ (metadata and short facts only)
        end
    end
    R->>R: switching for refused sources (other allowed sources only)
    R->>R: stories, remove facts marked Not important
    R->>V: validate every item, group by company
    V->>D: output/poc_RUN.json, companies/RUN/index.json, logs/RUN.json
    U->>UI: python -m atlas.companies --fetch-profiles --reports both
    UI->>G: each company's own website (contact / about pages)
    G->>W: robots.txt checked, 3 s apart, refused sites skipped
    UI->>D: company profiles, logos, one report per company
    U->>UI: open Overview, Search, Facts, Companies, Report
```

## 3. Stages, inputs and outputs

| Step | Module | Reads | Writes | Rule that matters most |
|---|---|---|---|---|
| 1 Gate | `compliance.py` | `sources.yaml`, robots.txt | refusals in the log | never fetch a refused site, 3 s between requests |
| 2 Discover (optional) | `scout/discover.py`, `vet.py`, `search_provider.py` | seeds, links, Firecrawl results | `scout/candidates.json` | a found source is never approved automatically |
| 3 Collect | `collect.py` | RSS feed or list page | `raw/` (metadata) | redirects re-checked, 429/503 stops the source |
| 4 Extract | `extract.py`, `company.py`, `htmlmeta.py` | page in memory | item fields | page text dropped, personal data scrubbed |
| 5 Clean | `clean.py` | items | `clean/` | dedupe by URL then fingerprint |
| 6 Filter | `filter.py` | items, settings | `facts/` | yes/no rules, every reason recorded |
| 7 Switch | `scout/fallback.py` | watchlist | `fallback_*` folders | other allowed sources only, labelled |
| 8 Stories | `scout/stories.py` | passed items | story ids | different companies never merged |
| 9 Validate | `validate.py` | items, stories, decisions | `validation` on each item | C1/C2/C3 criteria, blocks win |
| 10 Companies | `companies.py` | output | `companies/RUN/` | items without a company stay unattributed |
| 11 Profiles | `profile.py` | company websites | contacts, logo | company contacts only, role mailboxes only |
| 12 Reports | `report/*` | output, companies | `reports/` | numbers computed, text from templates |

## 4. Where each phase 3 task lives

| Task | Where |
|---|---|
| 1 Architecture and workflow | this file |
| 2 Company discovery | `atlas/company.py`, used by `atlas/extract.py` |
| 3 Content extraction | `atlas/extract.py` (`_main_text`, `page_headings`, `page_summary`, title and date fallbacks), `atlas/htmlmeta.py` |
| 4 Scraping tools | `docs/scraping_tools_evaluation.md`, `atlas/scout/search_provider.py` |
| 5 Blocked websites | research only: `docs/research_blocked_sites_and_agents.md` |
| 6 Company-wise classification | `atlas/companies.py`, Companies page |
| 7 Validation | `atlas/validate.py` |
| 8 Contacts and images | `atlas/profile.py`, `config/companies.yaml` |
| 9 Agentic approach | research only: `docs/research_blocked_sites_and_agents.md` |
| 10 Company reports | `atlas/report/company_report.py` |
