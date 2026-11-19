# Market Scout website

A React website (Vite) with a small local Python API. It shows the latest run, searches the facts, lets the team mark
facts and sources, edit the filters and build the brief. It reuses the team's own code (`atlas/` and `app/lib/`), so
it follows the same rules as the Streamlit app in `app/`.

## Run it
```powershell
cd web
npm install        # first time only
npm run dev        # starts the API (127.0.0.1:8765) and the site (http://127.0.0.1:5173)
```
Stop with Ctrl+C. It uses the repo's `.venv` and `.env`, so set those up first (see the main README).

## Run it as one connected app (frontend and backend together, with a password)
```powershell
cd web
npm start          # builds the site if needed, then serves site + API on http://127.0.0.1:8765
```
It prints the address and a login (user `scout`, a generated password; set `SCOUT_PASSWORD` to choose your own).
This is **local only**: it listens on 127.0.0.1, accepts only localhost host names, needs the password for every
request, and refuses non-JSON POSTs and requests from other sites. Do not expose it to the internet: it holds the
Databricks token and can start runs. `npm start -- --rebuild` rebuilds the site after you change it.

## How it works
- The browser calls `/api/...`; Vite forwards these to `web/api/server.py`, which runs on this laptop only (127.0.0.1).
- The Databricks token stays in `.env` and is read by the API. The browser never sees it.
- Saving filters, facts or sources starts a rerun with `python -m atlas.run`, like the Streamlit app does.
- Nothing is written to the laptop. Reports are built in memory, stored on the Volume and handed to the browser.

## Pages
Overview, Search, Facts, Sources, Filters, Report. Put the official Atlas Copco logo in `public/` as
`atlas_copco_logo.svg` or `.png` and it appears in the menu.

Environment: `ATLAS_REPO` (repo folder, only needed if web/ is moved), `SCOUT_API_PORT` (default 8765).
