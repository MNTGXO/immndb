from __future__ import annotations

import json
import re
from typing import Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from .models import CastMember, MovieDetails, MovieSearchResult


class IMDbClient:
    """IMDb scraper client for searching titles and collecting title details."""

    def __init__(self, *, mn_base_url: str = "https://www.imdb.com", mn_timeout: int = 20):
        self.mn_base_url = mn_base_url.rstrip("/")
        self.mn_timeout = mn_timeout
        self.mn_session = requests.Session()
        self.mn_session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (X11; Linux x86_64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                "Accept-Language": "en-US,en;q=0.9",
            }
        )

    def mn_search_movies(self, mn_query: str, *, mn_max_pages: int = 1) -> List[MovieSearchResult]:
        """Search IMDb titles and follow "More popular matches" pagination."""
        if not mn_query.strip():
            return []

        mntg_results: List[MovieSearchResult] = []
        mntg_seen_ids: set[str] = set()
        mntg_start = 1

        for _ in range(max(1, mn_max_pages)):
            mntg_params = {"q": mn_query, "s": "tt", "ttype": "ft", "ref_": "fn_ft"}
            if mntg_start > 1:
                mntg_params["start"] = str(mntg_start)

            mntg_response = self.mn_session.get(
                f"{self.mn_base_url}/find/", params=mntg_params, timeout=self.mn_timeout
            )
            mntg_response.raise_for_status()
            mntg_soup = BeautifulSoup(mntg_response.text, "html.parser")

            mntg_page_results = self._mn_parse_search_results_page(mntg_soup)
            if not mntg_page_results:
                break

            mntg_fresh_count = 0
            for mntg_item in mntg_page_results:
                if mntg_item.mn_imdb_id in mntg_seen_ids:
                    continue
                mntg_seen_ids.add(mntg_item.mn_imdb_id)
                mntg_results.append(mntg_item)
                mntg_fresh_count += 1

            if mntg_fresh_count == 0:
                break

            if not self._mn_has_more_matches_button(mntg_soup):
                break

            mntg_start += 50

        return mntg_results

    def search_movies(self, query: str, *, max_pages: int = 1) -> List[MovieSearchResult]:
        """Backward-compatible alias."""
        return self.mn_search_movies(query, mn_max_pages=max_pages)

    def mn_get_movie_details(self, mn_imdb_id_or_url: str) -> MovieDetails:
        mntgxo_id = self._mn_extract_imdb_id(mn_imdb_id_or_url)
        mntgxo_title_url = (
            mn_imdb_id_or_url
            if mn_imdb_id_or_url.startswith("http")
            else f"{self.mn_base_url}/title/{mntgxo_id}/"
        )
        mntgxo_ratings_url = f"{self.mn_base_url}/title/{mntgxo_id}/ratings/"
        mntgxo_plotsummary_url = f"{self.mn_base_url}/title/{mntgxo_id}/plotsummary/"

        mntgxo_title_soup = self._mn_fetch_soup(mntgxo_title_url)
        mntgxo_ratings_soup = self._mn_fetch_soup(mntgxo_ratings_url)
        mntgxo_plot_soup = self._mn_fetch_soup(mntgxo_plotsummary_url)

        mntgxo_ld_json = self._mn_extract_json_ld(mntgxo_title_soup)

        mn_title = mntgxo_ld_json.get("name") or self._mn_safe_text(mntgxo_title_soup.select_one("h1")) or mntgxo_id
        mn_year = self._mn_to_int(
            self._mn_deep_get(mntgxo_ld_json, ["datePublished"])[:4]
            if mntgxo_ld_json.get("datePublished")
            else self._mn_safe_text(mntgxo_title_soup.select_one('a[href*="/releaseinfo/"]'))
        )

        mn_rating, mn_votes = self._mn_extract_rating_votes(mntgxo_ratings_soup, mntgxo_ld_json)
        mn_storyline = self._mn_extract_plotsummary_story(mntgxo_plot_soup)
        mn_plot_preview = self._mn_safe_text(mntgxo_title_soup.select_one('[data-testid="plot-xs_to_m"]'))

        mn_directors, mn_writers, mn_stars = self._mn_extract_people_main_page(mntgxo_title_soup)

        mn_details = MovieDetails(
            mn_imdb_id=mntgxo_id,
            mn_title=mn_title,
            mn_original_title=self._mn_safe_text(mntgxo_title_soup.select_one('[data-testid="hero__pageTitle"] + div')),
            mn_year=mn_year,
            mn_rating=mn_rating,
            mn_votes=mn_votes,
            mn_storyline=mn_storyline,
            mn_plot_preview=mn_plot_preview,
            mn_genres=self._mn_extract_genres(mntgxo_title_soup, mntgxo_ld_json),
            mn_runtime=self._mn_extract_metadata_value(mntgxo_title_soup, "title-techspec_runtime"),
            mn_release_date=self._mn_extract_metadata_value(mntgxo_title_soup, "title-details-releasedate"),
            mn_certificate=self._mn_extract_metadata_value(mntgxo_title_soup, "storyline-certificate"),
            mn_cast=self._mn_parse_cast(mntgxo_title_soup, mntgxo_ld_json),
            mn_stars=mn_stars,
            mn_directors=mn_directors or self._mn_people_from_json(mntgxo_ld_json, "director"),
            mn_writers=mn_writers or self._mn_people_from_json(mntgxo_ld_json, "creator"),
            mn_budget=self._mn_extract_metadata_value(mntgxo_title_soup, "title-boxoffice-budget"),
            mn_gross_us_canada=self._mn_extract_metadata_value(mntgxo_title_soup, "title-boxoffice-grossdomestic"),
            mn_gross_worldwide=self._mn_extract_metadata_value(
                mntgxo_title_soup, "title-boxoffice-cumulativeworldwidegross"
            ),
            mn_country_of_origin=self._mn_extract_metadata_list(mntgxo_title_soup, "title-details-origin"),
            mn_languages=self._mn_extract_metadata_list(mntgxo_title_soup, "title-details-languages"),
            mn_production_companies=self._mn_extract_metadata_list(mntgxo_title_soup, "title-details-companies"),
            mn_aka=self._mn_extract_metadata_value(mntgxo_title_soup, "title-details-akas"),
            mn_streaming_links=self._mn_extract_streaming_links(mntgxo_title_soup),
            mn_url=mntgxo_title_url,
            mn_raw_sections={
                "title_html": mntgxo_title_url,
                "ratings_html": mntgxo_ratings_url,
                "plotsummary_html": mntgxo_plotsummary_url,
            },
        )
        return mn_details

    def get_movie_details(self, imdb_id_or_url: str) -> MovieDetails:
        """Backward-compatible alias."""
        return self.mn_get_movie_details(imdb_id_or_url)

    def _mn_fetch_soup(self, mn_url: str) -> BeautifulSoup:
        mntgxo_response = self.mn_session.get(mn_url, timeout=self.mn_timeout)
        mntgxo_response.raise_for_status()
        return BeautifulSoup(mntgxo_response.text, "html.parser")

    @staticmethod
    def _mn_extract_imdb_id(mn_value: str) -> str:
        mntg_match = re.search(r"(tt\d+)", mn_value)
        if not mntg_match:
            raise ValueError(f"Could not find IMDb id in: {mn_value}")
        return mntg_match.group(1)

    def _mn_parse_search_results_page(self, mn_soup: BeautifulSoup) -> List[MovieSearchResult]:
        mntg_out: List[MovieSearchResult] = []
        mntg_items = mn_soup.select("li.ipc-metadata-list-summary-item")

        for mntg_item in mntg_items:
            mntg_title_node = mntg_item.select_one("h3.ipc-title__text")
            mntg_link = mntg_item.select_one('a.ipc-lockup-overlay[href*="/title/"]') or mntg_item.select_one(
                'a.ipc-title-link-wrapper[href*="/title/"]'
            )
            if not mntg_title_node or not mntg_link:
                continue

            mntg_href = mntg_link.get("href", "")
            mntg_imdb_id = self._mn_extract_imdb_id(mntg_href)

            mntg_meta_bits = [
                mn_bit.get_text(strip=True)
                for mn_bit in mntg_item.select(".cli-title-metadata .ipc-inline-list__item")
            ]

            mntg_rating_raw = self._mn_safe_text(mntg_item.select_one(".ipc-rating-star--rating"))
            mntg_votes_raw = self._mn_safe_text(mntg_item.select_one(".ipc-rating-star--voteCount"))
            mntg_poster_node = mntg_item.select_one("img.ipc-image")

            mntg_out.append(
                MovieSearchResult(
                    mn_imdb_id=mntg_imdb_id,
                    mn_title=mntg_title_node.get_text(strip=True),
                    mn_year=self._mn_to_int(mntg_meta_bits[0] if mntg_meta_bits else None),
                    mn_duration=mntg_meta_bits[1] if len(mntg_meta_bits) > 1 else None,
                    mn_certificate=mntg_meta_bits[2] if len(mntg_meta_bits) > 2 else None,
                    mn_poster_url=mntg_poster_node.get("src") if mntg_poster_node else None,
                    mn_rating=self._mn_to_float(mntg_rating_raw),
                    mn_votes=mntg_votes_raw.strip("() ") if mntg_votes_raw else None,
                    mn_url=urljoin(self.mn_base_url, mntg_href.split("?")[0]),
                )
            )

        return mntg_out

    @staticmethod
    def _mn_has_more_matches_button(mn_soup: BeautifulSoup) -> bool:
        return bool(
            mn_soup.select_one(".find-see-more-title-btn .ipc-see-more__button")
            or mn_soup.find(string=lambda mn_t: mn_t and "More popular matches" in mn_t)
        )

    @staticmethod
    def _mn_extract_json_ld(mn_soup: BeautifulSoup) -> Dict:
        for mn_script in mn_soup.select('script[type="application/ld+json"]'):
            mn_text = mn_script.string
            if not mn_text:
                continue
            try:
                mntg_data = json.loads(mn_text)
            except json.JSONDecodeError:
                continue
            if isinstance(mntg_data, dict):
                return mntg_data
        return {}

    def _mn_extract_rating_votes(self, mn_ratings_soup: BeautifulSoup, mn_ld_json: Dict) -> tuple[Optional[float], Optional[int]]:
        mntg_rating_raw = self._mn_safe_text(
            mn_ratings_soup.select_one('[data-testid="rating-button__aggregate-rating__score"] span')
        )
        mntg_votes_raw = self._mn_safe_text(
            mn_ratings_soup.select_one('[data-testid="rating-button__aggregate-rating__score"] + div')
        )
        if not mntg_rating_raw:
            mntg_rating_raw = self._mn_deep_get(mn_ld_json, ["aggregateRating", "ratingValue"])
        if not mntg_votes_raw:
            mntg_votes_raw = self._mn_deep_get(mn_ld_json, ["aggregateRating", "ratingCount"])
        return self._mn_to_float(mntg_rating_raw), self._mn_to_int(mntg_votes_raw)

    def _mn_extract_plotsummary_story(self, mn_plot_soup: BeautifulSoup) -> Optional[str]:
        mntg_story = self._mn_safe_text(mn_plot_soup.select_one(".ipc-html-content-inner-div"))
        if mntg_story:
            return mntg_story
        return self._mn_safe_text(mn_plot_soup.select_one('[data-testid="sub-section-summaries"] li'))

    def _mn_extract_people_main_page(self, mn_title_soup: BeautifulSoup) -> tuple[List[str], List[str], List[str]]:
        mntg_directors: List[str] = []
        mntg_writers: List[str] = []
        mntg_stars: List[str] = []

        for mn_credit_item in mn_title_soup.select('[data-testid="title-pc-principal-credit"]'):
            mn_label_node = mn_credit_item.select_one(".ipc-metadata-list-item__label")
            mn_label = (self._mn_safe_text(mn_label_node) or "").lower()
            mn_names = [mn_a.get_text(strip=True) for mn_a in mn_credit_item.select("a.ipc-metadata-list-item__list-content-item--link")]

            if "director" in mn_label:
                mntg_directors.extend(mn_names)
            elif "writer" in mn_label:
                mntg_writers.extend(mn_names)
            elif "star" in mn_label:
                mntg_stars.extend(mn_names)

        return mntg_directors, mntg_writers, mntg_stars

    def _mn_extract_genres(self, mn_title_soup: BeautifulSoup, mn_ld_json: Dict) -> List[str]:
        mntg_genres = [
            mn_a.get_text(strip=True)
            for mn_a in mn_title_soup.select('[data-testid="storyline-genres"] a, [data-testid="genres"] a')
        ]
        if mntg_genres:
            return mntg_genres

        mntg_json_genres = mn_ld_json.get("genre")
        if isinstance(mntg_json_genres, list):
            return [str(mn_g) for mn_g in mntg_json_genres]
        if isinstance(mntg_json_genres, str):
            return [mntg_json_genres]
        return []

    def _mn_parse_cast(self, mn_title_soup: BeautifulSoup, mn_ld_json: Dict) -> List[CastMember]:
        mntg_cast: List[CastMember] = []

        for mn_cast_item in mn_title_soup.select('[data-testid="title-cast-item"]'):
            mn_actor_node = mn_cast_item.select_one('[data-testid="title-cast-item__actor"]')
            mn_character_node = mn_cast_item.select_one('[data-testid="cast-item-characters-link"]')
            mntg_cast.append(
                CastMember(
                    mn_name=self._mn_safe_text(mn_actor_node) or "Unknown",
                    mn_character=self._mn_safe_text(mn_character_node),
                    mn_url=urljoin(self.mn_base_url, mn_actor_node.get("href"))
                    if mn_actor_node and mn_actor_node.get("href")
                    else None,
                )
            )

        if mntg_cast:
            return mntg_cast

        mntg_actor_json = mn_ld_json.get("actor") if isinstance(mn_ld_json.get("actor"), list) else []
        for mn_actor in mntg_actor_json:
            if isinstance(mn_actor, dict):
                mntg_cast.append(CastMember(mn_name=mn_actor.get("name", "Unknown"), mn_url=mn_actor.get("url")))

        if mntg_cast:
            return mntg_cast

        mntg_stars = self._mn_extract_metadata_list(mn_title_soup, "title-pc-principal-credit")
        return [CastMember(mn_name=mn_star) for mn_star in mntg_stars]

    def _mn_extract_metadata_value(self, mn_soup: BeautifulSoup, mn_testid: str) -> Optional[str]:
        mn_item = mn_soup.select_one(f'[data-testid="{mn_testid}"]')
        if not mn_item:
            return None

        mn_link = mn_item.select_one(
            ".ipc-metadata-list-item__list-content-item--link, .ipc-metadata-list-item__list-content-item"
        )
        if mn_link:
            return self._mn_safe_text(mn_link)

        mn_span = mn_item.select_one("span.ipc-metadata-list-item__list-content-item")
        return self._mn_safe_text(mn_span)

    def _mn_extract_metadata_list(self, mn_soup: BeautifulSoup, mn_testid: str) -> List[str]:
        mn_item = mn_soup.select_one(f'[data-testid="{mn_testid}"]')
        if not mn_item:
            return []
        return [
            mn_node.get_text(strip=True)
            for mn_node in mn_item.select(
                ".ipc-metadata-list-item__list-content-item--link, span.ipc-metadata-list-item__list-content-item"
            )
        ]

    def _mn_extract_streaming_links(self, mn_soup: BeautifulSoup) -> List[str]:
        return [mn_a.get("href") for mn_a in mn_soup.select('[data-testid="tm-box-wb-shoveler"] a[href]') if mn_a.get("href")]

    @staticmethod
    def _mn_people_from_json(mn_data: Dict, mn_key: str) -> List[str]:
        mn_values = mn_data.get(mn_key)
        if not isinstance(mn_values, list):
            mn_values = [mn_values] if mn_values else []
        return [mn_person["name"] for mn_person in mn_values if isinstance(mn_person, dict) and mn_person.get("name")]

    @staticmethod
    def _mn_safe_text(mn_node) -> Optional[str]:
        return mn_node.get_text(strip=True) if mn_node else None

    @staticmethod
    def _mn_to_int(mn_value) -> Optional[int]:
        if mn_value is None:
            return None

        mn_str = str(mn_value).strip()
        mn_match = re.search(r"[\d,.]+\s*[KMB]", mn_str, flags=re.IGNORECASE)
        if mn_match:
            mn_num = float(re.sub(r"[^\d.]", "", mn_match.group(0)))
            mn_suffix = mn_match.group(0)[-1].upper()
            mn_mult = {"K": 1_000, "M": 1_000_000, "B": 1_000_000_000}.get(mn_suffix, 1)
            return int(mn_num * mn_mult)

        mn_digits = re.sub(r"[^\d]", "", mn_str)
        return int(mn_digits) if mn_digits else None

    @staticmethod
    def _mn_to_float(mn_value) -> Optional[float]:
        if mn_value is None:
            return None
        mn_match = re.search(r"\d+(?:\.\d+)?", str(mn_value))
        return float(mn_match.group(0)) if mn_match else None

    @staticmethod
    def _mn_deep_get(mn_data: Dict, mn_keys: List[str]):
        mn_cur = mn_data
        for mn_key in mn_keys:
            if not isinstance(mn_cur, dict):
                return None
            mn_cur = mn_cur.get(mn_key)
        return mn_cur
