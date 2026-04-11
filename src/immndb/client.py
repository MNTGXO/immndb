from __future__ import annotations

import json
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .models import CastMember, MovieDetails, MovieSearchResult


class IMDbClient:
    """Simple IMDb scraper client for search and title details."""

    def __init__(self, *, base_url: str = "https://www.imdb.com", timeout: int = 15):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def search_movies(self, query: str, *, max_pages: int = 1) -> List[MovieSearchResult]:
        """Search IMDb titles and return parsed movie search results.

        Supports pagination by requesting subsequent pages and by detecting
        the "More popular matches" section on result pages.
        """
        if not query.strip():
            return []

        results: List[MovieSearchResult] = []
        seen: set[str] = set()

        start = 1
        for _ in range(max_pages):
            params = {"q": query, "s": "tt", "ttype": "ft", "ref_": "fn_ft"}
            if start > 1:
                params["start"] = str(start)

            response = self.session.get(f"{self.base_url}/find/", params=params, timeout=self.timeout)
            response.raise_for_status()
            soup = BeautifulSoup(response.text, "html.parser")

            page_items = self._parse_search_results_page(soup)
            if not page_items:
                break

            fresh = 0
            for item in page_items:
                if item.imdb_id in seen:
                    continue
                seen.add(item.imdb_id)
                results.append(item)
                fresh += 1

            if fresh == 0:
                break

            has_more = self._has_more_matches_button(soup)
            if not has_more:
                break

            start += 50

        return results

    def get_movie_details(self, imdb_id_or_url: str) -> MovieDetails:
        imdb_id = self._extract_imdb_id(imdb_id_or_url)
        url = imdb_id_or_url if imdb_id_or_url.startswith("http") else f"{self.base_url}/title/{imdb_id}/"

        response = self.session.get(url, timeout=self.timeout)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")

        data = self._extract_json_ld(soup)
        title = data.get("name") or self._safe_text(soup.select_one("h1")) or imdb_id
        year = self._to_int(self._deep_get(data, ["datePublished"])[:4] if data.get("datePublished") else None)
        rating = self._to_float(self._deep_get(data, ["aggregateRating", "ratingValue"]))
        votes = self._to_int(self._deep_get(data, ["aggregateRating", "ratingCount"]))
        storyline = (
            self._safe_text(soup.select_one('[data-testid="plot-xl"]'))
            or self._safe_text(soup.select_one('[data-testid="plot-l"]'))
            or data.get("description")
        )

        cast = self._parse_cast(soup, data)
        genres = self._parse_genres(soup, data)

        return MovieDetails(
            imdb_id=imdb_id,
            title=title,
            original_title=self._safe_text(soup.select_one('[data-testid="hero__pageTitle"] + div')),
            year=year,
            rating=rating,
            votes=votes,
            storyline=storyline,
            genres=genres,
            runtime=self._safe_text(soup.select_one('[data-testid="title-techspec_runtime"] div.ipc-metadata-list-item__content-container')),
            release_date=self._safe_text(soup.select_one('[data-testid="title-details-releasedate"] .ipc-metadata-list-item__list-content-item')),
            cast=cast,
            directors=self._people_from_json(data, "director"),
            writers=self._people_from_json(data, "creator"),
            url=url,
        )

    @staticmethod
    def _extract_imdb_id(value: str) -> str:
        m = re.search(r"(tt\d+)", value)
        if not m:
            raise ValueError(f"Could not find IMDb id in: {value}")
        return m.group(1)

    def _parse_search_results_page(self, soup: BeautifulSoup) -> List[MovieSearchResult]:
        out: List[MovieSearchResult] = []
        items = soup.select("li.ipc-metadata-list-summary-item")

        for item in items:
            title_node = item.select_one("h3.ipc-title__text")
            link = item.select_one('a.ipc-lockup-overlay[href*="/title/"]') or item.select_one('a.ipc-title-link-wrapper[href*="/title/"]')
            if not title_node or not link:
                continue

            href = link.get("href", "")
            imdb_id = self._extract_imdb_id(href)

            meta_bits = [n.get_text(strip=True) for n in item.select(".cli-title-metadata .ipc-inline-list__item")]
            year = self._to_int(meta_bits[0] if meta_bits else None)
            duration = meta_bits[1] if len(meta_bits) > 1 else None
            certificate = meta_bits[2] if len(meta_bits) > 2 else None

            rating_raw = self._safe_text(item.select_one(".ipc-rating-star--rating"))
            votes_raw = self._safe_text(item.select_one(".ipc-rating-star--voteCount"))
            poster = item.select_one("img.ipc-image")

            out.append(
                MovieSearchResult(
                    imdb_id=imdb_id,
                    title=title_node.get_text(strip=True),
                    year=year,
                    duration=duration,
                    certificate=certificate,
                    poster_url=poster.get("src") if poster else None,
                    rating=self._to_float(rating_raw),
                    votes=votes_raw.strip("() ") if votes_raw else None,
                    url=urljoin(self.base_url, href.split("?")[0]),
                )
            )

        return out

    @staticmethod
    def _has_more_matches_button(soup: BeautifulSoup) -> bool:
        return bool(
            soup.select_one(".find-see-more-title-btn")
            or soup.find(string=lambda t: t and "More popular matches" in t)
        )

    @staticmethod
    def _extract_json_ld(soup: BeautifulSoup) -> Dict:
        for script in soup.select('script[type="application/ld+json"]'):
            text = script.string
            if not text:
                continue
            try:
                data = json.loads(text)
            except json.JSONDecodeError:
                continue
            if isinstance(data, dict):
                return data
        return {}

    def _parse_cast(self, soup: BeautifulSoup, data: Dict) -> List[CastMember]:
        cast: List[CastMember] = []

        for node in soup.select('[data-testid="title-cast-item"]'):
            actor = node.select_one('[data-testid="title-cast-item__actor"]')
            character = node.select_one('[data-testid="cast-item-characters-link"]')
            cast.append(
                CastMember(
                    name=self._safe_text(actor) or "Unknown",
                    character=self._safe_text(character),
                    url=urljoin(self.base_url, actor.get("href")) if actor and actor.get("href") else None,
                )
            )

        if cast:
            return cast

        actors = data.get("actor") if isinstance(data.get("actor"), list) else []
        for actor in actors:
            if not isinstance(actor, dict):
                continue
            cast.append(CastMember(name=actor.get("name", "Unknown"), url=actor.get("url")))

        return cast

    def _parse_genres(self, soup: BeautifulSoup, data: Dict) -> List[str]:
        genres = [n.get_text(strip=True) for n in soup.select('[data-testid="genres"] a')]
        if genres:
            return genres

        from_json = data.get("genre")
        if isinstance(from_json, list):
            return [str(g) for g in from_json]
        if isinstance(from_json, str):
            return [from_json]
        return []

    @staticmethod
    def _people_from_json(data: Dict, key: str) -> List[str]:
        values = data.get(key)
        if not isinstance(values, list):
            values = [values] if values else []
        out: List[str] = []
        for person in values:
            if isinstance(person, dict) and person.get("name"):
                out.append(person["name"])
        return out

    @staticmethod
    def _safe_text(node) -> Optional[str]:
        return node.get_text(strip=True) if node else None

    @staticmethod
    def _to_int(value) -> Optional[int]:
        if value is None:
            return None
        digits = re.sub(r"[^\d]", "", str(value))
        return int(digits) if digits else None

    @staticmethod
    def _to_float(value) -> Optional[float]:
        if value is None:
            return None
        match = re.search(r"\d+(?:\.\d+)?", str(value))
        return float(match.group(0)) if match else None

    @staticmethod
    def _deep_get(data: Dict, keys: List[str]):
        cur = data
        for key in keys:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(key)
        return cur
