from __future__ import annotations

import json
import os
import random
import sqlite3
import string
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import requests
from bson import ObjectId
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pymongo import MongoClient
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes

from immndb import IMDbClient

DB_PATH = Path(os.getenv("DB_PATH", "movies.db"))
MONGO_URI = os.getenv("MONGO_URI", "")
MONGO_DB_NAME = os.getenv("MONGO_DB_NAME", "moviehub")
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
BOT_ADMIN_IDS = {
    int(chunk.strip())
    for chunk in os.getenv("BOT_ADMIN_IDS", "").split(",")
    if chunk.strip().isdigit()
}
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "*")
DATA_PROVIDER = os.getenv("DATA_PROVIDER", "package").lower()  # package|api
OMDB_API_KEY = os.getenv("OMDB_API_KEY", "")


@dataclass
class PendingAdd:
    user_id: int
    chat_id: int
    download_url: str
    year: int | None
    lang: str | None
    thumb_url: str | None


class MovieOut(BaseModel):
    id: str
    imdb_id: str
    title: str
    year: int | None = None
    lang: str | None = None
    thumbnail_url: str | None = None
    download_url: str
    rating: float | None = None
    votes: str | None = None
    genres: list[str] = []
    storyline: str | None = None
    runtime: str | None = None
    created_at: str


class ListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[MovieOut]


class MovieProvider:
    def search(self, query: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def details(self, imdb_id: str) -> dict[str, Any]:
        raise NotImplementedError


class PackageIMDbProvider(MovieProvider):
    def __init__(self) -> None:
        self.client = IMDbClient()

    def search(self, query: str) -> list[dict[str, Any]]:
        rows = self.client.mn_search_movies(query, mn_max_pages=1)[:6]
        return [
            {"imdb_id": r.mn_imdb_id, "title": r.mn_title, "year": r.mn_year}
            for r in rows
        ]

    def details(self, imdb_id: str) -> dict[str, Any]:
        d = self.client.mn_get_movie_details(imdb_id)
        return {
            "imdb_id": d.mn_imdb_id,
            "title": d.mn_title,
            "year": d.mn_year,
            "lang": (d.mn_languages[0] if d.mn_languages else None),
            "rating": d.mn_rating,
            "votes": d.mn_votes,
            "genres": d.mn_genres or [],
            "storyline": d.mn_storyline,
            "runtime": d.mn_runtime,
        }


class OmdbApiProvider(MovieProvider):
    def search(self, query: str) -> list[dict[str, Any]]:
        res = requests.get(
            "https://www.omdbapi.com/",
            params={"apikey": OMDB_API_KEY, "s": query, "type": "movie"},
            timeout=20,
        )
        res.raise_for_status()
        data = res.json()
        if data.get("Response") == "False":
            return []
        return [
            {
                "imdb_id": item.get("imdbID"),
                "title": item.get("Title"),
                "year": int(item.get("Year", "0")[:4]) if item.get("Year") else None,
            }
            for item in data.get("Search", [])[:6]
        ]

    def details(self, imdb_id: str) -> dict[str, Any]:
        res = requests.get(
            "https://www.omdbapi.com/",
            params={"apikey": OMDB_API_KEY, "i": imdb_id, "plot": "full"},
            timeout=20,
        )
        res.raise_for_status()
        d = res.json()
        if d.get("Response") == "False":
            raise ValueError(d.get("Error", "Movie not found"))
        return {
            "imdb_id": d.get("imdbID"),
            "title": d.get("Title"),
            "year": int(str(d.get("Year", "0"))[:4]) if d.get("Year") else None,
            "lang": (d.get("Language", "").split(",")[0].strip() or None),
            "rating": float(d["imdbRating"]) if d.get("imdbRating") not in (None, "N/A") else None,
            "votes": d.get("imdbVotes"),
            "genres": [g.strip() for g in d.get("Genre", "").split(",") if g.strip()],
            "storyline": d.get("Plot"),
            "runtime": d.get("Runtime"),
        }


class MovieStore:
    def upsert(self, movie: dict[str, Any]) -> str:
        raise NotImplementedError

    def list_movies(self, search: str | None, lang: str | None, year: int | None, page: int, page_size: int) -> tuple[int, list[dict[str, Any]]]:
        raise NotImplementedError

    def get_movie(self, movie_id: str) -> dict[str, Any] | None:
        raise NotImplementedError

    def list_languages(self) -> list[str]:
        raise NotImplementedError


class SQLiteStore(MovieStore):
    def __init__(self) -> None:
        self.init_db()

    def _db(self) -> sqlite3.Connection:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self) -> None:
        conn = self._db()
        try:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS movies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    imdb_id TEXT UNIQUE NOT NULL,
                    title TEXT NOT NULL,
                    year INTEGER,
                    lang TEXT,
                    thumbnail_url TEXT,
                    download_url TEXT NOT NULL,
                    rating REAL,
                    votes TEXT,
                    genres TEXT,
                    storyline TEXT,
                    runtime TEXT,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.commit()
        finally:
            conn.close()

    def upsert(self, movie: dict[str, Any]) -> str:
        conn = self._db()
        try:
            conn.execute(
                """
                INSERT INTO movies
                (imdb_id, title, year, lang, thumbnail_url, download_url, rating, votes,
                 genres, storyline, runtime, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(imdb_id) DO UPDATE SET
                  title=excluded.title,
                  year=excluded.year,
                  lang=excluded.lang,
                  thumbnail_url=excluded.thumbnail_url,
                  download_url=excluded.download_url,
                  rating=excluded.rating,
                  votes=excluded.votes,
                  genres=excluded.genres,
                  storyline=excluded.storyline,
                  runtime=excluded.runtime,
                  created_at=excluded.created_at
                """,
                (
                    movie["imdb_id"],
                    movie["title"],
                    movie.get("year"),
                    movie.get("lang"),
                    movie.get("thumbnail_url"),
                    movie["download_url"],
                    movie.get("rating"),
                    movie.get("votes"),
                    json.dumps(movie.get("genres", [])),
                    movie.get("storyline"),
                    movie.get("runtime"),
                    datetime.utcnow().isoformat(),
                ),
            )
            conn.commit()
            row = conn.execute("SELECT id FROM movies WHERE imdb_id = ?", [movie["imdb_id"]]).fetchone()
            return str(row[0])
        finally:
            conn.close()

    def _row_to_dict(self, row: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": str(row["id"]),
            "imdb_id": row["imdb_id"],
            "title": row["title"],
            "year": row["year"],
            "lang": row["lang"],
            "thumbnail_url": row["thumbnail_url"],
            "download_url": row["download_url"],
            "rating": row["rating"],
            "votes": row["votes"],
            "genres": json.loads(row["genres"] or "[]"),
            "storyline": row["storyline"],
            "runtime": row["runtime"],
            "created_at": row["created_at"],
        }

    def list_movies(self, search: str | None, lang: str | None, year: int | None, page: int, page_size: int) -> tuple[int, list[dict[str, Any]]]:
        where, params = [], []
        if search:
            where.append("LOWER(title) LIKE ?")
            params.append(f"%{search.lower()}%")
        if lang:
            where.append("LOWER(lang) = ?")
            params.append(lang.lower())
        if year:
            where.append("year = ?")
            params.append(year)
        clause = f"WHERE {' AND '.join(where)}" if where else ""
        offset = (page - 1) * page_size

        conn = self._db()
        try:
            total = conn.execute(f"SELECT COUNT(*) FROM movies {clause}", params).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM movies {clause} ORDER BY id DESC LIMIT ? OFFSET ?",
                [*params, page_size, offset],
            ).fetchall()
            return total, [self._row_to_dict(r) for r in rows]
        finally:
            conn.close()

    def get_movie(self, movie_id: str) -> dict[str, Any] | None:
        conn = self._db()
        try:
            row = conn.execute("SELECT * FROM movies WHERE id = ?", [movie_id]).fetchone()
            return self._row_to_dict(row) if row else None
        finally:
            conn.close()

    def list_languages(self) -> list[str]:
        conn = self._db()
        try:
            rows = conn.execute(
                "SELECT DISTINCT lang FROM movies WHERE lang IS NOT NULL AND lang != '' ORDER BY lang"
            ).fetchall()
            return [r[0] for r in rows]
        finally:
            conn.close()


class MongoStore(MovieStore):
    def __init__(self) -> None:
        client = MongoClient(MONGO_URI)
        self.col = client[MONGO_DB_NAME]["movies"]
        self.col.create_index("imdb_id", unique=True)

    def upsert(self, movie: dict[str, Any]) -> str:
        movie = {**movie, "created_at": datetime.utcnow().isoformat()}
        self.col.update_one({"imdb_id": movie["imdb_id"]}, {"$set": movie}, upsert=True)
        doc = self.col.find_one({"imdb_id": movie["imdb_id"]}, {"_id": 1})
        return str(doc["_id"])

    def _norm(self, d: dict[str, Any]) -> dict[str, Any]:
        d = dict(d)
        d["id"] = str(d.pop("_id"))
        d.setdefault("genres", [])
        return d

    def list_movies(self, search: str | None, lang: str | None, year: int | None, page: int, page_size: int) -> tuple[int, list[dict[str, Any]]]:
        q: dict[str, Any] = {}
        if search:
            q["title"] = {"$regex": search, "$options": "i"}
        if lang:
            q["lang"] = {"$regex": f"^{lang}$", "$options": "i"}
        if year:
            q["year"] = year
        total = self.col.count_documents(q)
        cur = self.col.find(q).sort("_id", -1).skip((page - 1) * page_size).limit(page_size)
        return total, [self._norm(x) for x in cur]

    def get_movie(self, movie_id: str) -> dict[str, Any] | None:
        try:
            q = {"_id": ObjectId(movie_id)}
        except Exception:
            return None
        d = self.col.find_one(q)
        return self._norm(d) if d else None

    def list_languages(self) -> list[str]:
        return sorted([x for x in self.col.distinct("lang") if x])


def parse_add_args(raw: str) -> tuple[str, str, int | None, str | None, str | None]:
    tokens = raw.split()
    if len(tokens) < 2:
        raise ValueError("Usage: /add <download_url> <title> [year] [lang] [thumbnail_url]")
    download_url = tokens[0]
    thumb = tokens[-1] if tokens[-1].startswith("http") and len(tokens) >= 3 else None
    working = tokens[1:-1] if thumb else tokens[1:]

    year = next((int(t) for t in working if t.isdigit() and len(t) == 4), None)
    if year:
        working.remove(str(year))

    lang = working[-1].lower() if working and working[-1].isalpha() and len(working[-1]) <= 20 else None
    if lang:
        working = working[:-1]

    title = " ".join(working).strip()
    if not title:
        raise ValueError("Movie title is required")
    return download_url, title, year, lang, thumb


def pick_store() -> MovieStore:
    return MongoStore() if MONGO_URI else SQLiteStore()


def pick_provider() -> MovieProvider:
    if DATA_PROVIDER == "api" and OMDB_API_KEY:
        return OmdbApiProvider()
    return PackageIMDbProvider()


PENDING: dict[str, PendingAdd] = {}
STORE = pick_store()
PROVIDER = pick_provider()
telegram_app: Application | None = None


def _random_id(size: int = 10) -> str:
    chars = string.ascii_letters + string.digits
    return "".join(random.choice(chars) for _ in range(size))


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if update.effective_user.id not in BOT_ADMIN_IDS:
        await update.message.reply_text("You are not allowed to use this bot.")
        return
    await update.message.reply_text("Admin ready. Use /add <download_url> <title> [year] [lang] [thumbnail_url]")


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_user is None or update.message is None:
        return
    if update.effective_user.id not in BOT_ADMIN_IDS:
        await update.message.reply_text("Only bot admins can add movies.")
        return
    try:
        download_url, title, year, lang, thumb = parse_add_args(" ".join(context.args))
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return

    query = f"{title} {year}" if year else title
    results = PROVIDER.search(query)
    if not results:
        await update.message.reply_text("No movie candidates found.")
        return

    req_id = _random_id()
    PENDING[req_id] = PendingAdd(update.effective_user.id, update.effective_chat.id, download_url, year, lang, thumb)
    buttons = [[InlineKeyboardButton(text=f"{r['title']} ({r.get('year') or '?'})", callback_data=f"pick:{req_id}:{r['imdb_id']}")] for r in results]
    await update.message.reply_text("Select correct movie:", reply_markup=InlineKeyboardMarkup(buttons))


async def on_pick(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.from_user is None:
        return
    await query.answer()

    parts = (query.data or "").split(":")
    if len(parts) != 3:
        await query.edit_message_text("Invalid request")
        return
    req_id, imdb_id = parts[1], parts[2]
    pending = PENDING.get(req_id)
    if not pending:
        await query.edit_message_text("Request expired")
        return
    if query.from_user.id != pending.user_id or query.from_user.id not in BOT_ADMIN_IDS:
        await query.edit_message_text("Not allowed")
        return

    details = PROVIDER.details(imdb_id)
    movie = {
        "imdb_id": details["imdb_id"],
        "title": details["title"],
        "year": pending.year or details.get("year"),
        "lang": pending.lang or details.get("lang"),
        "thumbnail_url": pending.thumb_url,
        "download_url": pending.download_url,
        "rating": details.get("rating"),
        "votes": details.get("votes"),
        "genres": details.get("genres", []),
        "storyline": details.get("storyline"),
        "runtime": details.get("runtime"),
    }
    STORE.upsert(movie)
    PENDING.pop(req_id, None)
    await query.edit_message_text(f"✅ Added/updated: {movie['title']}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_app
    if BOT_TOKEN:
        telegram_app = Application.builder().token(BOT_TOKEN).build()
        telegram_app.add_handler(CommandHandler("start", cmd_start))
        telegram_app.add_handler(CommandHandler("add", cmd_add))
        telegram_app.add_handler(CallbackQueryHandler(on_pick, pattern=r"^pick:"))
        await telegram_app.initialize()
        await telegram_app.start()
        await telegram_app.updater.start_polling()
    yield
    if telegram_app:
        await telegram_app.updater.stop()
        await telegram_app.stop()
        await telegram_app.shutdown()


app = FastAPI(title="Movie Download API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN] if FRONTEND_ORIGIN != "*" else ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "storage": "mongo" if MONGO_URI else "sqlite", "provider": DATA_PROVIDER}


@app.get("/api/movies", response_model=ListResponse)
def list_movies(
    search: str | None = None,
    lang: str | None = None,
    year: int | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    total, items = STORE.list_movies(search, lang, year, page, page_size)
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@app.get("/api/movies/{movie_id}", response_model=MovieOut)
def get_movie(movie_id: str):
    movie = STORE.get_movie(movie_id)
    if not movie:
        raise HTTPException(status_code=404, detail="Movie not found")
    return movie


@app.get("/api/meta/languages")
def list_languages() -> dict[str, list[str]]:
    return {"items": STORE.list_languages()}
