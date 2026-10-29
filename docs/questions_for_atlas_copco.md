# Questions for Atlas Copco (Friday 30 Oct 2026)

Ten questions, in the order we would like to ask them. For each: why we ask, and what we do with the answer.

---

**1. Please approve or change our 5 proposed sources. Which sources do you trust, and which should we avoid?**
- *Why we ask:* every source stays "proposed" until you approve it; we only run sources you sign off.
- *What we do with the answer:* mark approved sources `approved`, remove or replace the others, and rerun.

**2. Can you give us a Databricks or Azure workspace so the data stays in your environment?**
- *Why we ask:* you asked that data is not stored locally. Today it sits in a free student Databricks workspace, which is for non-commercial use only.
- *What we do with the answer:* point the pipeline at your workspace (it only needs a host, a token and a volume name) and delete our test data.

**3. What should the summary report look like? Do you have a template?**
- *Why we ask:* the report (PPT or PDF) is a later phase; we want to build the right shape from the start.
- *What we do with the answer:* design the report fields and layout around your template.

**4. Is there a narrower compressor topic you want first?**
- *Why we ask:* our scope is "industrial compressor technology". A narrower start (for example oil-free, or variable speed drive) gives sharper results.
- *What we do with the answer:* tune the keyword list and the technology labels to that topic.

**5. Is a weekly run the right frequency?**
- *Why we ask:* it affects how often we touch each website and how much data you receive.
- *What we do with the answer:* set the schedule and the "recent" window to match.

**6. Who in your Legal team reviews the source list?**
- *Why we ask:* some sites forbid automated access or are unclear, and your Legal team should review the list before go-live.
- *What we do with the answer:* send them our vetting document (robots.txt, terms and a short quote for every source).

**7. Is it fine for the AI step to use a hosted model, or must it be self-hosted?**
- *Why we ask:* Friday's pipeline uses no AI. The later summary step needs a model, and the choice depends on your data policy.
- *What we do with the answer:* design the AI step around a hosted API or a self-hosted model, whichever you allow.

**8. Some sites do not let us read them. Do you have a licence, a feed or a preferred route for them?**
- *Why we ask:* in our check, CAGI, PR Newswire and Plant Services forbid automated access in their terms. Ingersoll Rand, Plant Engineering and Business Wire refused our requests (HTTP 403 or 429) with no ban stated. Ingersoll Rand is a major US competitor.
- *What we do with the answer:* ask the owners for permission with your backing, or use a licensed feed you already have.

**9. Should "industrial" be a required word for an item to pass, and is 12 months the right "recent" window?**
- *Why we ask:* today an item passes if it is about compressors, in North America, from a credible source and published in the last 12 months. "Industrial" is only a flag.
- *What we do with the answer:* make "industrial" a requirement, or keep it a flag, and change the window if you prefer.

**10. How should we show "fact" versus "claim" in the report?**
- *Why we ask:* we label an item "claim" when a company says it about itself (most newsroom posts) and "fact" when a neutral or official source states it.
- *What we do with the answer:* decide whether claims are shown, grouped, or ranked lower in the report.
