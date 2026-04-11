# Advanced Movie Website + Telegram Admin Bot

This project is now an advanced **movie downloading website** with:
- animated frontend website
- FastAPI backend
- Telegram admin bot workflow to upload/edit/publish movies
- MongoDB support with SQLite fallback
- metadata source choice: API mode (OMDb) or package mode (`immndb`)

---

## Required Environment Variables

```bash
BOT_TOKEN=<telegram bot token>
BOT_ADMIN_IDS=123456789,987654321
FRONTEND_ORIGIN=*

# optional
MONGO_URI=<mongodb uri>
MONGO_DB_NAME=moviehub
DATA_PROVIDER=api          # api or package
OMDB_API_KEY=<omdb key>    # required if DATA_PROVIDER=api
```

---

## Your requested bot flow (implemented)

### 1) Add movie
Use:
```bash
/addmovie <movie name>
```

Bot replies with IMDb results (buttons). You select one.

### 2) Upload links + thumbnail
After selection, bot creates a **draft** and asks you to send a **photo** with caption like:
```text
{Download url}|{language}|{quality}|;{2nd Download url}|{language}|{2nd quality}|
```
- supports multiple lines and `;` separated links
- creates a **special id** (e.g. `MVAB12CD34`)

### 3) Confirm/publish
```bash
/publish <special_id>
```
Movie becomes visible on website.

---

## Advanced bot commands

- `/start` → show admin command help
- `/addmovie <movie name>` → create draft from IMDb match
- `/editmovie <special_id>` → open inline edit actions (title/lang/thumbnail/links)
- `/addlink <special_id> <url>|<language>|<quality>|` → append link(s)
- `/publish <special_id>` → publish to website
- `/unpublish <special_id>` → hide from website (back to draft)
- `/deletemovie <special_id>` → remove movie
- `/listmovies` → list latest movies + statuses

---

## Website behavior

- search movies instantly
- language filter
- advanced animated cards + modal
- each movie page/modal shows all download links with language + quality
- thumbnails support Telegram-uploaded images via backend media endpoint

---

## API Endpoints

- `GET /health`
- `GET /api/movies?search=&lang=&page=&page_size=`
- `GET /api/movies/{special_id}` (published only)
- `GET /api/meta/languages`
- `GET /api/media/{telegram_file_id}`

---

## DB behavior

- If `MONGO_URI` is set → uses MongoDB
- Else → uses SQLite (`movies.db`)

---

## Metadata source behavior

- `DATA_PROVIDER=api` + `OMDB_API_KEY` → OMDb API
- Else → `immndb` package scraping mode

---

## Run locally (terminal)

```bash
git clone <repo>
cd immndb
python -m venv .venv
source .venv/bin/activate
pip install -e .
pip install -r requirements-web.txt

export BOT_TOKEN="..."
export BOT_ADMIN_IDS="123...,456..."
uvicorn backend_app:app --host 0.0.0.0 --port 8000 --reload
```

Run frontend:
```bash
python -m http.server 5173
```
Open `http://localhost:5173/frontend/`.
Set `frontend/config.js` to your backend URL.

---

## Deploy support

### Koyeb
- install: `pip install -e . -r requirements-web.txt`
- run: `uvicorn backend_app:app --host 0.0.0.0 --port 8000`
- use `koyeb.yaml`

### Render
- use `render.yaml`

### Railway
- use `railway.json`

### Heroku
- use `Procfile`

### Vercel (frontend)
- use `vercel.json`
- set backend URL in `frontend/config.js`

### VPS
- run uvicorn with systemd + nginx reverse proxy

### Termux
- install python/git, then same local run steps

---

## Legal note

Only upload and distribute movies/content you are legally authorized to share.
