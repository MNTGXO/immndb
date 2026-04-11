# Movie Download Website (Backend + Frontend)

This repo is now a **full movie downloading website stack**:

- **Backend API** (FastAPI) for movie list/search/details and Telegram admin ingestion.
- **Frontend website** (static, animated) for users to browse and open direct links.
- **Split hosting support**: backend on Koyeb/Render/Railway/Heroku/VPS, frontend on Vercel.

---

## 1) Core Features

- Admin-only Telegram bot (`BOT_ADMIN_IDS`) can add movies with direct link.
- `/add <download_url> <title> [year] [lang] [thumbnail_url]` flow.
- Bot shows candidate IMDb matches; admin chooses the correct one.
- Website auto-updates because movies are stored in DB and served via API.
- Frontend features:
  - animated cards and background
  - search bar
  - language filter
  - year filter
  - details modal
  - direct download button

---

## 2) Data source mode (API OR package)

You can choose movie metadata source:

### A) `DATA_PROVIDER=package` (default)
Uses local Python package `immndb` (scraping-based).

### B) `DATA_PROVIDER=api`
Uses **OMDb API** directly (not package), requires `OMDB_API_KEY`.

Env:

```bash
export DATA_PROVIDER=api
export OMDB_API_KEY=your_omdb_key
```

If API key is missing, backend automatically falls back to package mode.

---

## 3) Database mode (Mongo first, SQLite fallback)

### A) MongoDB (preferred)
If `MONGO_URI` is set, backend uses MongoDB.

```bash
export MONGO_URI="mongodb+srv://user:pass@cluster.mongodb.net/?retryWrites=true&w=majority"
export MONGO_DB_NAME="moviehub"
```

### B) SQLite fallback
If `MONGO_URI` is not set, backend uses `movies.db` SQLite automatically.

---

## 4) Local run (Terminal / Linux / macOS / Windows WSL)

```bash
git clone <your-repo-url>
cd immndb
python -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -r requirements-web.txt
```

Set env:

```bash
export BOT_TOKEN="<telegram_bot_token>"
export BOT_ADMIN_IDS="12345678,87654321"
export FRONTEND_ORIGIN="*"
# optional:
# export MONGO_URI="..."
# export DATA_PROVIDER="api"
# export OMDB_API_KEY="..."
```

Run backend:

```bash
uvicorn backend_app:app --host 0.0.0.0 --port 8000 --reload
```

Run frontend static server:

```bash
python -m http.server 5173
```

Open: `http://localhost:5173/frontend/`

Set backend URL in `frontend/config.js`.

---

## 5) Termux deployment (Android)

```bash
pkg update && pkg upgrade -y
pkg install git python -y
git clone <your-repo-url>
cd immndb
python -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -r requirements-web.txt
```

Then same env vars + run uvicorn:

```bash
uvicorn backend_app:app --host 0.0.0.0 --port 8000
```

Use a tunnel (Cloudflare Tunnel/ngrok) if you need public URL.

---

## 6) Koyeb deployment (backend)

1. Push repo to GitHub.
2. In Koyeb: **Create App → GitHub**.
3. Select service root and set install command:
   - `pip install -e . -r requirements-web.txt`
4. Run command:
   - `uvicorn backend_app:app --host 0.0.0.0 --port 8000`
5. Add env vars:
   - `BOT_TOKEN`, `BOT_ADMIN_IDS`, `FRONTEND_ORIGIN`
   - optional `MONGO_URI`, `MONGO_DB_NAME`, `DATA_PROVIDER`, `OMDB_API_KEY`

`koyeb.yaml` is included for infra-as-code deployment.

---

## 7) Render deployment (backend)

1. New **Web Service** from repo.
2. Build command:
   - `pip install -e . -r requirements-web.txt`
3. Start command:
   - `uvicorn backend_app:app --host 0.0.0.0 --port $PORT`
4. Add same env vars.

---

## 8) Railway deployment (backend)

1. `railway init` and connect repo.
2. Set start command:
   - `uvicorn backend_app:app --host 0.0.0.0 --port $PORT`
3. Add environment variables in Railway dashboard.
4. Deploy with:

```bash
railway up
```

---

## 9) Heroku deployment (backend)

`Procfile` included.

```bash
heroku create <app-name>
heroku config:set BOT_TOKEN=... BOT_ADMIN_IDS=... FRONTEND_ORIGIN=...
# optional
heroku config:set MONGO_URI=... MONGO_DB_NAME=moviehub DATA_PROVIDER=api OMDB_API_KEY=...
git push heroku main
```

---

## 10) VPS deployment (backend)

On Ubuntu VPS:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv nginx

git clone <your-repo-url>
cd immndb
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -r requirements-web.txt
```

Create systemd service for uvicorn (recommended), then reverse proxy with Nginx to port 8000.

---

## 11) Vercel deployment (frontend)

1. Import repo in Vercel.
2. Keep frontend files in `frontend/`.
3. `vercel.json` rewrites all routes to `frontend/index.html`.
4. Update `frontend/config.js`:

```js
window.APP_CONFIG = {
  API_BASE_URL: "https://your-backend-domain.example.com",
};
```

Deploy.

---

## 12) Telegram bot usage

Use:

```bash
/add https://your-link/movie.mkv kgf 2 2022 malayalam https://image-url/poster.jpg
```

Then tap the correct movie from returned candidate buttons.

---

## 13) API Endpoints

- `GET /health`
- `GET /api/movies?search=&lang=&year=&page=&page_size=`
- `GET /api/movies/{movie_id}`
- `GET /api/meta/languages`

---

## 14) Important note

Only add legal content and direct links that you are authorized to distribute.
