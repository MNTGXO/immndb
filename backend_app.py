from __future__ import annotations

import json
import os
import random
import re
import sqlite3
import string
import sys
from contextlib import asynccontextmanager
from datetime import datetime
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pymongo import MongoClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.error import Conflict
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

ROOT_DIR = Path(__file__).resolve().parent
SRC_DIR = ROOT_DIR / "src"
if SRC_DIR.exists() and str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

try:
    from immndb import IMDbClient
except Exception:
    IMDbClient = None  # type: ignore

DB_PATH = Path(os.getenv("DB_PATH", "movies.db"))
MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "moviehub")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_ADMIN_IDS = {int(x) for x in os.getenv("BOT_ADMIN_IDS", "").split(",") if x.strip().isdigit()}
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "*")
DATA_PROVIDER = os.getenv("DATA_PROVIDER", "package").lower()  # package|api
OMDB_API_KEY = os.getenv("OMDB_API_KEY", "")
ENABLE_BOT_POLLING = os.getenv("ENABLE_BOT_POLLING", "1").lower() in {"1", "true", "yes"}
FRONTEND_PUBLIC_URL = os.getenv("FRONTEND_PUBLIC_URL", "").strip()
EMBED_FRONTEND = os.getenv("EMBED_FRONTEND", "1").lower() in {"1", "true", "yes"}


def now_iso() -> str:
    return datetime.utcnow().isoformat()


def rand_id(prefix: str = "MV", size: int = 8) -> str:
    return f"{prefix}{''.join(random.choice(string.ascii_uppercase + string.digits) for _ in range(size))}"


def normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9\s]", " ", (value or "").lower())).strip()


def parse_links(text: str) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    chunks = [c.strip() for line in text.splitlines() for c in line.split(";") if c.strip()]
    for chunk in chunks:
        parts = [p.strip() for p in chunk.split("|") if p.strip()]
        if len(parts) < 3:
            continue
        links.append({"url": parts[0], "language": parts[1], "quality": parts[2]})
    return links




def imdb_suggestion_search(query: str, limit: int = 8) -> list[dict[str, Any]]:
    q = query.strip().lower()
    if not q:
        return []
    first = q[0]
    url = f"https://v3.sg.media-imdb.com/suggestion/{first}/{requests.utils.quote(q)}.json"
    try:
        r = requests.get(url, timeout=15)
        data = r.json()
    except Exception:
        return []
    items = []
    for row in data.get("d", []):
        imdb_id = row.get("id")
        title = row.get("l")
        year = row.get("y")
        if imdb_id and title and str(imdb_id).startswith("tt"):
            items.append({"imdb_id": imdb_id, "title": title, "year": year})
        if len(items) >= limit:
            break
    return items
class Provider:
    def search(self, q: str) -> list[dict[str, Any]]: ...
    def details(self, imdb_id: str) -> dict[str, Any]: ...


class PackageProvider(Provider):
    def __init__(self) -> None:
        if IMDbClient is None:
            raise RuntimeError("immndb is not importable. Set PYTHONPATH=src or use DATA_PROVIDER=api with OMDB_API_KEY.")
        self.c = IMDbClient()

    def search(self, q: str) -> list[dict[str, Any]]:
        variants = [q.strip(), f"{q.strip()} movie", q.strip().replace("  ", " ")]
        out: list[dict[str, Any]] = []
        seen: set[str] = set()
        for query in variants:
            if not query:
                continue
            try:
                rows = self.c.mn_search_movies(query, mn_max_pages=2)[:12]
            except Exception:
                rows = []
            for x in rows:
                if x.mn_imdb_id in seen:
                    continue
                seen.add(x.mn_imdb_id)
                out.append({"imdb_id": x.mn_imdb_id, "title": x.mn_title, "year": x.mn_year})
                if len(out) >= 8:
                    return out
        if out:
            return out
        return imdb_suggestion_search(q, limit=8)

    def details(self, imdb_id: str) -> dict[str, Any]:
        d = self.c.mn_get_movie_details(imdb_id)
        return {
            "imdb_id": d.mn_imdb_id,
            "title": d.mn_title,
            "year": d.mn_year,
            "genres": d.mn_genres or [],
            "storyline": d.mn_storyline,
            "rating": d.mn_rating,
            "votes": d.mn_votes,
            "runtime": d.mn_runtime,
            "lang": d.mn_languages[0] if d.mn_languages else None,
        }


class OmdbProvider(Provider):
    def search(self, q: str) -> list[dict[str, Any]]:
        r = requests.get("https://www.omdbapi.com/", params={"apikey": OMDB_API_KEY, "s": q, "type": "movie"}, timeout=20)
        data = r.json()
        if data.get("Response") == "False":
            return []
        return [{"imdb_id": i.get("imdbID"), "title": i.get("Title"), "year": int(str(i.get("Year", "0"))[:4]) if i.get("Year") else None} for i in data.get("Search", [])[:8]]

    def details(self, imdb_id: str) -> dict[str, Any]:
        r = requests.get("https://www.omdbapi.com/", params={"apikey": OMDB_API_KEY, "i": imdb_id, "plot": "full"}, timeout=20)
        d = r.json()
        return {
            "imdb_id": d.get("imdbID"),
            "title": d.get("Title"),
            "year": int(str(d.get("Year", "0"))[:4]) if d.get("Year") else None,
            "genres": [g.strip() for g in str(d.get("Genre", "")).split(",") if g.strip()],
            "storyline": d.get("Plot"),
            "rating": float(d["imdbRating"]) if d.get("imdbRating") not in ("N/A", None) else None,
            "votes": d.get("imdbVotes"),
            "runtime": d.get("Runtime"),
            "lang": str(d.get("Language", "")).split(",")[0].strip() or None,
        }


class Store:
    def create_draft(self, base: dict[str, Any]) -> dict[str, Any]: ...
    def update(self, special_id: str, patch: dict[str, Any]) -> dict[str, Any] | None: ...
    def get(self, special_id: str) -> dict[str, Any] | None: ...
    def list(self, search: str | None, lang: str | None, page: int, page_size: int, include_unpublished: bool) -> tuple[int, list[dict[str, Any]]]: ...
    def delete(self, special_id: str) -> bool: ...


class SQLiteStore(Store):
    def __init__(self) -> None:
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS movies (
                  id INTEGER PRIMARY KEY AUTOINCREMENT,
                  special_id TEXT UNIQUE,
                  imdb_id TEXT,
                  title TEXT,
                  year INTEGER,
                  lang TEXT,
                  thumbnail TEXT,
                  downloads TEXT,
                  genres TEXT,
                  storyline TEXT,
                  rating REAL,
                  votes TEXT,
                  runtime TEXT,
                  status TEXT,
                  created_at TEXT,
                  updated_at TEXT
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def _db(self):
        c = sqlite3.connect(DB_PATH)
        c.row_factory = sqlite3.Row
        return c

    def _norm(self, r: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(r["id"]), "special_id": r["special_id"], "imdb_id": r["imdb_id"], "title": r["title"], "year": r["year"],
            "lang": r["lang"], "thumbnail": r["thumbnail"], "downloads": json.loads(r["downloads"] or "[]"), "genres": json.loads(r["genres"] or "[]"),
            "storyline": r["storyline"], "rating": r["rating"], "votes": r["votes"], "runtime": r["runtime"], "status": r["status"],
            "created_at": r["created_at"], "updated_at": r["updated_at"],
        }

    def create_draft(self, base: dict[str, Any]) -> dict[str, Any]:
        sid = rand_id()
        payload = {
            "special_id": sid, "status": "draft", "downloads": [], "thumbnail": None,
            "lang": base.get("lang"), "created_at": now_iso(), "updated_at": now_iso(), **base,
        }
        conn = self._db()
        try:
            conn.execute(
                "INSERT INTO movies (special_id, imdb_id, title, year, lang, thumbnail, downloads, genres, storyline, rating, votes, runtime, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                [payload["special_id"], payload.get("imdb_id"), payload.get("title"), payload.get("year"), payload.get("lang"), payload.get("thumbnail"), json.dumps(payload["downloads"]), json.dumps(payload.get("genres", [])), payload.get("storyline"), payload.get("rating"), payload.get("votes"), payload.get("runtime"), payload["status"], payload["created_at"], payload["updated_at"]],
            )
            conn.commit()
            return self.get(sid)  # type: ignore
        finally:
            conn.close()

    def update(self, special_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        existing = self.get(special_id)
        if not existing:
            return None
        merged = {**existing, **patch, "updated_at": now_iso()}
        conn = self._db()
        try:
            conn.execute(
                "UPDATE movies SET title=?, year=?, lang=?, thumbnail=?, downloads=?, genres=?, storyline=?, rating=?, votes=?, runtime=?, status=?, updated_at=? WHERE special_id=?",
                [merged.get("title"), merged.get("year"), merged.get("lang"), merged.get("thumbnail"), json.dumps(merged.get("downloads", [])), json.dumps(merged.get("genres", [])), merged.get("storyline"), merged.get("rating"), merged.get("votes"), merged.get("runtime"), merged.get("status"), merged.get("updated_at"), special_id],
            )
            conn.commit()
            return self.get(special_id)
        finally:
            conn.close()

    def get(self, special_id: str) -> dict[str, Any] | None:
        conn = self._db()
        try:
            r = conn.execute("SELECT * FROM movies WHERE special_id = ?", [special_id]).fetchone()
            return self._norm(r) if r else None
        finally:
            conn.close()

    def list(self, search: str | None, lang: str | None, page: int, page_size: int, include_unpublished: bool) -> tuple[int, list[dict[str, Any]]]:
        where = []
        params = []
        if not include_unpublished:
            where.append("status IN ('published','pending')")
        if search:
            where.append("LOWER(title) LIKE ?")
            params.append(f"%{search.lower()}%")
        if lang:
            where.append("LOWER(lang)=?")
            params.append(lang.lower())
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        off = (page - 1) * page_size
        conn = self._db()
        try:
            total = conn.execute(f"SELECT COUNT(*) FROM movies {clause}", params).fetchone()[0]
            rows = conn.execute(f"SELECT * FROM movies {clause} ORDER BY id DESC LIMIT ? OFFSET ?", [*params, page_size, off]).fetchall()
            return total, [self._norm(r) for r in rows]
        finally:
            conn.close()

    def delete(self, special_id: str) -> bool:
        conn = self._db()
        try:
            cur = conn.execute("DELETE FROM movies WHERE special_id = ?", [special_id])
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


class MongoStore(Store):
    def __init__(self) -> None:
        c = MongoClient(MONGO_URI)
        self.col = c[MONGO_DB_NAME]["movies"]
        self.col.create_index("special_id", unique=True)

    def create_draft(self, base: dict[str, Any]) -> dict[str, Any]:
        d = {"special_id": rand_id(), "status": "draft", "downloads": [], "thumbnail": None, "created_at": now_iso(), "updated_at": now_iso(), **base}
        self.col.insert_one(d)
        return self.get(d["special_id"])  # type: ignore

    def update(self, special_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        self.col.update_one({"special_id": special_id}, {"$set": {**patch, "updated_at": now_iso()}})
        return self.get(special_id)

    def _norm(self, d: dict[str, Any]) -> dict[str, Any]:
        d = dict(d)
        d["id"] = str(d.pop("_id"))
        d.setdefault("downloads", [])
        d.setdefault("genres", [])
        return d

    def get(self, special_id: str) -> dict[str, Any] | None:
        d = self.col.find_one({"special_id": special_id})
        return self._norm(d) if d else None

    def list(self, search: str | None, lang: str | None, page: int, page_size: int, include_unpublished: bool) -> tuple[int, list[dict[str, Any]]]:
        q: dict[str, Any] = {}
        if not include_unpublished:
            q["status"] = {"$in": ["published", "pending"]}
        if search:
            q["title"] = {"$regex": re.escape(search), "$options": "i"}
        if lang:
            q["lang"] = {"$regex": f"^{re.escape(lang)}$", "$options": "i"}
        total = self.col.count_documents(q)
        items = [self._norm(x) for x in self.col.find(q).sort("_id", -1).skip((page - 1) * page_size).limit(page_size)]
        return total, items

    def delete(self, special_id: str) -> bool:
        return self.col.delete_one({"special_id": special_id}).deleted_count > 0


if DATA_PROVIDER == "api" and OMDB_API_KEY:
    PROVIDER: Provider = OmdbProvider()
else:
    try:
        PROVIDER = PackageProvider()
    except Exception:
        if OMDB_API_KEY:
            PROVIDER = OmdbProvider()
        else:
            raise
STORE: Store = MongoStore() if MONGO_URI else SQLiteStore()
PENDING_PICK: dict[str, dict[str, Any]] = {}
AWAITING: dict[int, dict[str, str]] = {}
telegram_app: Application | None = None




async def ensure_admin(update: Update) -> bool:
    if update.effective_user is None or update.message is None:
        return False
    if update.effective_user.id not in BOT_ADMIN_IDS:
        await update.message.reply_text("Access denied. Add your Telegram user id to BOT_ADMIN_IDS.")
        return False
    return True




def _search_existing_movies(query: str, limit: int = 4) -> list[dict[str, Any]]:
    q = normalize_text(query)
    if not q:
        return []
    _, items = STORE.list(None, None, 1, 500, True)
    out: list[dict[str, Any]] = []
    for item in items:
        title = normalize_text(str(item.get("title") or ""))
        if not title:
            continue
        if q in title or any(tok and tok in title for tok in q.split(" ")):
            out.append({"imdb_id": item.get("imdb_id"), "title": item.get("title"), "year": item.get("year")})
        if len(out) >= limit:
            break
    return out


class MovieOut(BaseModel):
    special_id: str
    imdb_id: str | None = None
    title: str
    year: int | None = None
    lang: str | None = None
    thumbnail: str | None = None
    downloads: list[dict[str, str]] = []
    genres: list[str] = []
    storyline: str | None = None
    rating: float | None = None
    votes: str | None = None
    runtime: str | None = None
    status: str


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_admin(update):
        return
    await update.message.reply_text(
        "Admin commands:\n"
        "/addmovie <movie name>\n/editmovie <special_id>\n/addlink <special_id> <url>|<lang>|<quality>|\n"
        "/publish <special_id>\n/unpublish <special_id>\n/deletemovie <special_id>\n/listmovies"
    )


async def cmd_addmovie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_admin(update):
        return
    q = " ".join(context.args).strip()
    if not q:
        await update.message.reply_text("Usage: /addmovie <movie name>")
        return
    results = PROVIDER.search(q)
    existing = _search_existing_movies(q)
    if existing:
        known = {r.get("imdb_id") for r in results}
        for x in existing:
            if x.get("imdb_id") and x.get("imdb_id") in known:
                continue
            results.append(x)
            if len(results) >= 10:
                break
    if not results:
        await update.message.reply_text("No results found. Try full title or a different spelling.")
        return
    req = rand_id("REQ", 6)
    PENDING_PICK[req] = {"admin_id": update.effective_user.id, "results": results}
    kb = [[InlineKeyboardButton(f"{r['title']} ({r.get('year') or '?'})", callback_data=f"picknew:{req}:{r['imdb_id']}")] for r in results]
    await update.message.reply_text("Select movie:", reply_markup=InlineKeyboardMarkup(kb))


async def on_picknew(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if q is None or q.from_user is None:
        return
    await q.answer()
    _, req, imdb_id = (q.data or "").split(":")
    p = PENDING_PICK.get(req)
    if not p or q.from_user.id != p["admin_id"]:
        await q.edit_message_text("Request expired")
        return
    d = PROVIDER.details(imdb_id)
    movie = STORE.create_draft(d)
    AWAITING[q.from_user.id] = {"mode": "await_photo_links", "special_id": movie["special_id"]}
    await q.edit_message_text(
        f"Draft created: {movie['special_id']}\n"
        "Now send a photo with caption format:\n"
        "url|language|quality|;url2|language|quality| (multi links supported)\n"
        "After that use /publish <special_id>."
    )


async def on_photo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    st = AWAITING.get(update.effective_user.id)
    if not st or st.get("mode") != "await_photo_links":
        return
    special_id = st["special_id"]
    caption = update.message.caption or ""
    links = parse_links(caption)
    if not links:
        await update.message.reply_text("Caption invalid. Use url|language|quality|;url2|language|quality|")
        return
    photo = update.message.photo[-1] if update.message.photo else None
    thumb = f"tg:{photo.file_id}" if photo else None
    patch = {"thumbnail": thumb, "downloads": links, "lang": links[0].get("language", "").lower(), "status": "published"}
    movie = STORE.update(special_id, patch)
    AWAITING.pop(update.effective_user.id, None)
    await update.message.reply_text(f"Saved movie {special_id} and published it. Use /unpublish {special_id} if needed.")
    if movie:
        await update.message.reply_text(f"Special ID: {movie['special_id']}")


async def cmd_publish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_status(update, context, "published")


async def cmd_unpublish(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_status(update, context, "draft")


async def _set_status(update: Update, context: ContextTypes.DEFAULT_TYPE, status: str) -> None:
    if not await ensure_admin(update):
        return
    if not context.args:
        await update.message.reply_text(f"Usage: /{'publish' if status == 'published' else 'unpublish'} <special_id>")
        return
    sid = context.args[0]
    m = STORE.update(sid, {"status": status})
    await update.message.reply_text("Done" if m else "Not found")


async def cmd_addlink(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_admin(update):
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addlink <special_id> <url>|<language>|<quality>|")
        return
    sid = context.args[0]
    link_text = " ".join(context.args[1:])
    links = parse_links(link_text)
    if not links:
        await update.message.reply_text("Invalid link format")
        return
    m = STORE.get(sid)
    if not m:
        await update.message.reply_text("Movie not found")
        return
    m2 = STORE.update(sid, {"downloads": [*m.get("downloads", []), *links]})
    await update.message.reply_text(f"Added {len(links)} link(s) to {sid}" if m2 else "Failed")


async def cmd_editmovie(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /editmovie <special_id>")
        return
    sid = context.args[0]
    m = STORE.get(sid)
    if not m:
        await update.message.reply_text("Movie not found")
        return
    text = f"{sid}\n{m['title']} ({m.get('year')})\nStatus: {m.get('status')}\nLinks: {len(m.get('downloads', []))}"
    kb = [[InlineKeyboardButton("Edit title", callback_data=f"edit:{sid}:title"), InlineKeyboardButton("Edit lang", callback_data=f"edit:{sid}:lang")], [InlineKeyboardButton("Replace links", callback_data=f"edit:{sid}:links"), InlineKeyboardButton("Set thumb URL", callback_data=f"edit:{sid}:thumb")]]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(kb))


async def on_edit_cb(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if q is None or q.from_user is None:
        return
    await q.answer()
    _, sid, field = (q.data or "").split(":")
    AWAITING[q.from_user.id] = {"mode": f"edit_{field}", "special_id": sid}
    await q.edit_message_text(f"Send new value for {field}")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    st = AWAITING.get(update.effective_user.id)
    if not st:
        return
    sid, mode, text = st["special_id"], st["mode"], update.message.text.strip()
    patch: dict[str, Any] = {}
    if mode == "edit_title":
        patch["title"] = text
    elif mode == "edit_lang":
        patch["lang"] = text.lower()
    elif mode == "edit_thumb":
        patch["thumbnail"] = text
    elif mode == "edit_links":
        links = parse_links(text)
        if not links:
            await update.message.reply_text("Invalid links format")
            return
        patch["downloads"] = links
    else:
        return
    m = STORE.update(sid, patch)
    AWAITING.pop(update.effective_user.id, None)
    await update.message.reply_text("Updated" if m else "Movie not found")


async def cmd_delete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_admin(update):
        return
    if not context.args:
        await update.message.reply_text("Usage: /deletemovie <special_id>")
        return
    ok = STORE.delete(context.args[0])
    await update.message.reply_text("Deleted" if ok else "Not found")


async def cmd_listmovies(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not await ensure_admin(update):
        return
    _, items = STORE.list(None, None, 1, 20, True)
    txt = "\n".join([f"{m['special_id']} | {m['title']} | {m.get('status')}" for m in items]) or "No movies"
    await update.message.reply_text(txt)


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app
    if BOT_TOKEN and ENABLE_BOT_POLLING:
        telegram_app = Application.builder().token(BOT_TOKEN).build()
        telegram_app.add_handler(CommandHandler("start", cmd_start))
        telegram_app.add_handler(CommandHandler("addmovie", cmd_addmovie))
        telegram_app.add_handler(CommandHandler("editmovie", cmd_editmovie))
        telegram_app.add_handler(CommandHandler("addlink", cmd_addlink))
        telegram_app.add_handler(CommandHandler("publish", cmd_publish))
        telegram_app.add_handler(CommandHandler("unpublish", cmd_unpublish))
        telegram_app.add_handler(CommandHandler("deletemovie", cmd_delete))
        telegram_app.add_handler(CommandHandler("listmovies", cmd_listmovies))
        telegram_app.add_handler(CallbackQueryHandler(on_picknew, pattern=r"^picknew:"))
        telegram_app.add_handler(CallbackQueryHandler(on_edit_cb, pattern=r"^edit:"))
        telegram_app.add_handler(MessageHandler(filters.PHOTO, on_photo))
        telegram_app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
        await telegram_app.initialize()
        await telegram_app.bot.delete_webhook(drop_pending_updates=False)
        await telegram_app.start()
        try:
            await telegram_app.updater.start_polling()
        except Conflict:
            print("Telegram polling conflict detected. Disable polling on duplicate instances or scale to 1 worker.")
    yield
    if telegram_app:
        await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()


app = FastAPI(title="Movie Website API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN] if FRONTEND_ORIGIN != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)




if EMBED_FRONTEND:
    frontend_dir = ROOT_DIR / "frontend"
    if frontend_dir.exists():
        app.mount("/assets", StaticFiles(directory=str(frontend_dir)), name="assets")


@app.get("/")
def root_index():
    if EMBED_FRONTEND and (ROOT_DIR / "frontend" / "index.html").exists():
        return FileResponse(ROOT_DIR / "frontend" / "index.html")
    return {"message": "Movie API is running", "hint": "Set EMBED_FRONTEND=1 and keep frontend folder for same-domain UI."}


@app.get("/app")
def app_index():
    return root_index()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "storage": "mongo" if MONGO_URI else "sqlite", "provider": DATA_PROVIDER, "embed_frontend": EMBED_FRONTEND, "frontend_public_url": FRONTEND_PUBLIC_URL or None}


@app.get("/api/movies")
def api_list_movies(
    search: str | None = None,
    lang: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(24, ge=1, le=100),
    include_unpublished: bool = False,
):
    total, items = STORE.list(search, lang, page, page_size, include_unpublished)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@app.get("/api/movies/{special_id}")
def api_get_movie(special_id: str):
    m = STORE.get(special_id)
    if not m:
        raise HTTPException(404, "Movie not found")
    if m.get("status") not in {"published", "pending"}:
        raise HTTPException(403, "Movie not published")
    return m


@app.get("/api/meta/languages")
def api_langs():
    _, items = STORE.list(None, None, 1, 500, True)
    langs = sorted({(x.get("lang") or "").lower() for x in items if x.get("lang")})
    return {"items": langs}


@app.get("/api/media/{file_id}")
async def api_media(file_id: str):
    if not telegram_app or not BOT_TOKEN:
        raise HTTPException(404, "Bot not configured")
    f = await telegram_app.bot.get_file(file_id)
    b = BytesIO(await f.download_as_bytearray())
    b.seek(0)
    return StreamingResponse(b, media_type="image/jpeg")
