# Deploying the Market Scout website and backend

One container runs everything: the Python server serves the built website and the API. The pipeline reruns as a
subprocess of the same container. Data stays on the Databricks Volume; the container keeps nothing.

## Before you deploy (decisions for the team)
- The team rule is "do not host the app publicly". Deploying makes the site reachable from the internet, so Nikhil (repo
  owner) and your faculty should agree first.
- The app holds a Databricks token and can start runs that visit other companies' websites. Use a **separate token with a
  short life** for the deployment, and a **sandbox prefix** (`dev/<name>`), not the real demo folders.
- Every request needs the password. Choose a long one (16+ characters) and share it only with the people who need it.
  10 wrong passwords block an address for 10 minutes.

## Option A: Render (simplest)
1. The code must be in a GitHub repository that Render can read (a fork you own, or Nikhil's repo with his permission).
   Commit and push `Dockerfile`, `.dockerignore`, `render.yaml` and `web/`.
2. In Render: New, Blueprint, pick the repository. Render reads `render.yaml`.
3. Fill in the secrets Render asks for: `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `CONTACT_EMAIL`, `ATLAS_PATH_PREFIX`
   (for example `dev/ragini`) and `SCOUT_PASSWORD`.
4. Deploy. The first build takes several minutes (it installs the language model). Use at least the `starter` plan: the
   free plan has too little memory for a pipeline rerun.
5. Open the address Render gives you, for example `https://market-scout.onrender.com`. The browser asks for a login:
   user `scout`, and your `SCOUT_PASSWORD`.

## Option B: any Docker host or VM
```
docker build -t market-scout .
docker run -p 8765:10000 -e PORT=10000 \
  -e SCOUT_PASSWORD=... -e SCOUT_ALLOWED_HOSTS=your.domain.com \
  -e DATABRICKS_HOST=... -e DATABRICKS_TOKEN=... -e DATABRICKS_CATALOG=atlas_poc \
  -e DATABRICKS_SCHEMA=default -e DATABRICKS_VOLUME=data -e CONTACT_EMAIL=... -e ATLAS_PATH_PREFIX=dev/yourname \
  market-scout
```
Put it behind HTTPS (the host's proxy or a reverse proxy). The password is sent with every request, so never serve it
over plain HTTP on the internet.

## Environment variables
| Name | Purpose |
|---|---|
| `SCOUT_PASSWORD` | Required on a public address. The server refuses to start without it. |
| `SCOUT_ALLOWED_HOSTS` | Comma-separated public host names the server accepts (Render's name is added automatically). |
| `PORT` | The port to listen on (the host sets it). |
| `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_CATALOG`, `DATABRICKS_SCHEMA`, `DATABRICKS_VOLUME` | The Volume. |
| `CONTACT_EMAIL` | Put in the User-Agent every site sees. The pipeline stops without it. |
| `ATLAS_PATH_PREFIX` | `dev/<name>` for a sandbox; empty means the real demo folders. |

## What the server enforces
- A password on every page and API call (except `/healthz`, which reveals nothing).
- Only JSON POSTs, and nothing from another website's page (Origin check).
- Only the listed host names, a login throttle, and no-sniff / no-frame / no-referrer headers.

## Known limits
- One shared password, no per-person accounts, no audit log.
- A full pipeline run takes 15 to 25 minutes inside the container; the page shows progress, and a redeploy during a run
  stops it.
- The pipeline and its model need roughly 1 to 2 GB of memory.
- If the site is public, anyone with the password can press Done and start a run against other companies' websites.
  Share it carefully.
