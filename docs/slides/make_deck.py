"""Builds docs/slides/nikhil_pages_16_21.pptx: Nikhil's pages for the group deck (pages 16 to 21).
Run: python docs/slides/make_deck.py   (needs python-pptx). Images come from docs/images/. Opens in PowerPoint and in
Canva (Upload, then Import). Content only about what was built: records, storage, filter, switching, stories."""
from pathlib import Path

from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

HERE = Path(__file__).parent
IMG = HERE.parent / "images"
NAVY, BLUE, PALE, ROW, GREY = RGBColor(0x1F, 0x2A, 0x44), RGBColor(0x2F, 0x5A, 0xA8), RGBColor(0xDA, 0xE5, 0xF1), RGBColor(0xF5, 0xF8, 0xFC), RGBColor(0x55, 0x55, 0x55)
TITLE_FONT, BODY_FONT = "Poppins", "Open Sans"

prs = Presentation()
prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)


def slide(title: str):
    s = prs.slides.add_slide(prs.slide_layouts[6])
    bar = s.shapes.add_shape(1, 0, 0, Inches(0.3), prs.slide_height)
    bar.fill.solid(); bar.fill.fore_color.rgb = RGBColor(0x8F, 0xB8, 0xF5); bar.line.fill.background()
    tb = s.shapes.add_textbox(Inches(0.7), Inches(0.35), Inches(12), Inches(0.9)).text_frame
    r = tb.paragraphs[0].add_run()
    r.text, r.font.size, r.font.bold, r.font.name, r.font.color.rgb = title, Pt(32), True, TITLE_FONT, NAVY
    return s


def note(s, text, top=6.75, size=13, bold=False, left=0.7, width=12):
    tf = s.shapes.add_textbox(Inches(left), Inches(top), Inches(width), Inches(0.5)).text_frame
    tf.word_wrap = True
    r = tf.paragraphs[0].add_run()
    r.text, r.font.size, r.font.bold, r.font.name, r.font.color.rgb = text, Pt(size), bold, BODY_FONT, BLUE if bold else GREY


def table(s, left, top, width, cols, header, rows, size=12, row_h=0.5, header_h=None):
    shape = s.shapes.add_table(len(rows) + 1, len(cols), Inches(left), Inches(top), Inches(width), Inches(row_h * (len(rows) + 1)))
    t = shape.table
    total = sum(cols)
    for i, c in enumerate(cols):
        t.columns[i].width = Inches(width * c / total)
    for r_i, row in enumerate([header] + rows):
        for c_i, value in enumerate(row):
            cell = t.cell(r_i, c_i)
            cell.fill.solid(); cell.fill.fore_color.rgb = PALE if r_i == 0 else (ROW if r_i % 2 else RGBColor(255, 255, 255))
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE
            cell.margin_left = cell.margin_right = Inches(0.1)
            tf = cell.text_frame
            tf.word_wrap = True
            run = tf.paragraphs[0].add_run()
            run.text = value
            run.font.size, run.font.name = Pt(size), BODY_FONT
            run.font.bold = r_i == 0 or c_i == 0
            run.font.color.rgb = NAVY if (r_i == 0 or c_i == 0) else RGBColor(0x22, 0x22, 0x22)
    if header_h:
        t.rows[0].height = Inches(header_h)
        for i in range(1, len(rows) + 1):
            t.rows[i].height = Inches(row_h)
    return t


# ---- 16 ----
s = slide("My part: the core of the system")
table(s, 0.7, 1.4, 11.9, [3.3, 8.6], ["Module", "What it does"], [
    ["models.py", "Defines every record in one place, so all the code fits together"],
    ["settings.py, storage.py", "Reads the private settings; reads and writes the Databricks Volume"],
    ["filter.py", "Decides keep or drop, and records the reasons"],
    ["scout/settings_store.py", "Saves and loads the team's filters and decisions"],
    ["scout/fallback.py", "Switching: follows a company elsewhere when its own source refuses"],
    ["scout/stories.py", "Groups items about the same event into one story"],
    ["review.py", "Saves which facts are important and which sources are confirmed"],
    ["run.py", "Runs every step in order and writes the results and the log"],
    ["report/brief.py + the 4-page app", "The brief (facts, sources, why it matters) and the Dashboard, Sources, Facts, Report pages"],
], size=13, row_h=0.52)
note(s, "Rules inside, no AI model. Every decision can be explained.", top=6.7, bold=True)

# ---- 17 ----
s = slide("What one evidence record holds")
table(s, 0.7, 1.4, 11.9, [3.0, 8.9], ["Group", "Fields"], [
    ["Where it came from", "source name and type, link, licence note, time collected"],
    ["What it says", "title, publish date, company, product, technology, up to 3 short facts (200 characters each), fact or claim"],
    ["Signals for the filter", "compressor words found, names a US place, industrial hint"],
    ["Added in Phase 2", "region, type of news, story, switched-from source, watchlist names found"],
    ["The verdict", "the four checks, kept or dropped, every reason"],
    ["Privacy", "names, emails and phone numbers removed; a content fingerprint (a hash) is kept instead of the text"],
], size=14, row_h=0.62)
note(s, "The page text is never stored. A value that cannot be found stays empty, never guessed.", top=6.0, size=16, bold=True)

# ---- 18 ----
s = slide("How the information is stored")
s.shapes.add_picture(str(IMG / "nikhil_storage.png"), Inches(0.6), Inches(1.4), width=Inches(6.2))
table(s, 7.0, 1.4, 5.9, [1.7, 4.2], ["Folder", "Holds"], [
    ["source_register", "the sources used in the run"],
    ["raw", "what was collected: link, title, status (no text)"],
    ["clean", "every cleaned item with its filter result"],
    ["facts", "only the items that passed"],
    ["output", "the final results: sources, items, stories, settings used"],
    ["logs", "gate decisions, refusals, errors, notes"],
    ["settings", "saved filters, fact decisions, source confirmations"],
    ["scout", "sites the scout found and the team's decisions"],
    ["reports", "generated PPTX and PDF files"],
], size=11, row_h=0.46)
note(s, "JSON files, one per source per run, named by the run id. Each person works in their own prefix, so nobody overwrites the demo data.", top=6.55, size=12)

# ---- 19 ----
s = slide("The filter: what is inside")
table(s, 0.7, 1.4, 11.9, [2.4, 7.0, 2.5], ["Check", "The rule", "Reason if it fails"], [
    ["Compressor-related", "One of 44 compressor words in the title or text (compressor, compressed air, rotary screw, centrifugal compressor...), plus any extra words you add", "no_compressor_keyword"],
    ["North America", "The source is based in the US, Canada or Mexico, or the text names one of 69 places (28 US, 22 Canadian, 19 Mexican)", "not_north_america"],
    ["Credible source", "The source is vetted as working and is proposed or approved, not blocked", "source_not_credible"],
    ["Recent", "Published within the last N months (default 12). No date, or a date in the future, fails", "date_missing, date_in_future, too_old"],
], size=13, row_h=0.85, header_h=0.5)
note(s, "An item passes only if all four checks pass. Words match whole words, in any letter case.", top=5.85, size=14)
note(s, "\"Industrial\" (6 words: industrial, manufacturing, factory, plant, process, heavy-duty) is a flag only, not a gate.", top=6.4, size=14)

# ---- 20 ----
s = slide("Your settings add six more rules")
s.shapes.add_picture(str(IMG / "nikhil_filter.png"), Inches(0.5), Inches(1.5), width=Inches(7.5))
table(s, 8.2, 1.5, 4.8, [2.3, 2.5], ["Setting", "Reason if it fails"], [
    ["Regions (US, CA, MX)", "region_not_selected"],
    ["Technologies", "technology_not_selected"],
    ["Types of news", "event_type_not_selected"],
    ["Words to leave out", "excluded_keyword"],
    ["Industrial only", "not_industrial"],
    ["Source types", "source_type_not_selected"],
], size=11, row_h=0.55)
note(s, "Every failed check is listed, not only the first. With no settings the filter behaves exactly as before. Default regions: US and Canada.", top=5.7, size=13)
note(s, "A dropped item stays in clean/ with all its reasons; only kept items go into the results.", top=6.3, size=13)

# ---- 21 ----
s = slide("Switching and stories: the rules inside")
table(s, 0.7, 1.35, 11.9, [2.6, 9.3], ["Switching", "Rule"], [
    ["When", "A source is refused by the gate, returns zero pages, or hits a rate limit (429 or 503)"],
    ["Who we follow", "A watchlist entry (name or alias, whole word) that matches the source's company"],
    ["What we keep", "Up to 40 new pages per other allowed source, only items that name the company in the title, key facts or company field"],
    ["Never", "The refused site, its subdomains, web archives, caches, translation pages or proxies"],
], size=12, row_h=0.5)
table(s, 0.7, 4.1, 11.9, [2.6, 9.3], ["Stories", "Rule"], [
    ["Join when", "Same company, and the same product or the same type of news with similar titles (4 or more words), within 10 days"],
    ["Never join", "Different companies, or two items whose only link is the catch-all type \"other\""],
    ["Story id", "A fixed code from the earliest item and the company, so it stays the same between runs"],
], size=12, row_h=0.5)

out = HERE / "nikhil_pages_16_21.pptx"
prs.save(out)
print("wrote", out)
