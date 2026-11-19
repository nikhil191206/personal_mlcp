# Market Scout website and backend as one container: the Python server serves the built React site and the API.
# Build:  docker build -t market-scout .
# Run:    docker run -p 8765:10000 -e PORT=10000 -e SCOUT_PASSWORD=... -e DATABRICKS_HOST=... (see web/DEPLOY.md)

# Stage 1: build the website
FROM node:22-slim AS web
WORKDIR /w
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

# Stage 2: the Python backend with the pipeline
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt starlette uvicorn \
 && python -m spacy download en_core_web_sm
COPY . .
COPY --from=web /w/dist /app/web/dist
ENV SCOUT_SERVE=1 SCOUT_HOST=0.0.0.0 ATLAS_REPO=/app
CMD ["python", "web/api/server.py"]
