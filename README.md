# immndb

`immndb` is a Python package to collect IMDb-based movie information.

## What it does

- Search from IMDb find page (`/find/?q=...`) and collect all movie titles.
- Supports the **More popular matches** next button style pagination.
- Open a selected title (`/title/tt.../`) and enrich data using:
  - `/title/<id>/ratings/` for aggregate rating + vote count
  - `/title/<id>/plotsummary/` for full story text
  - main title page for release date, genres, cast/stars, credits, certificate,
    box office, runtime, language, origin, companies, and streaming links.

## Install

```bash
pip install -e .
```

## Usage

```python
from immndb import IMDbClient

mn_client = IMDbClient()

# Search movie list
mn_results = mn_client.mn_search_movies("kgf", mn_max_pages=3)
for mn_item in mn_results:
    print(mn_item.mn_imdb_id, mn_item.mn_title, mn_item.mn_year, mn_item.mn_rating)

# Pick one movie and fetch complete details
if mn_results:
    mn_details = mn_client.mn_get_movie_details(mn_results[0].mn_imdb_id)
    print(mn_details.mn_title)
    print(mn_details.mn_rating, mn_details.mn_votes)
    print(mn_details.mn_storyline)
    print(mn_details.mn_release_date)
    print(mn_details.mn_directors)
    print(mn_details.mn_writers)
    print(mn_details.mn_stars)
    print([mn_cast.mn_name for mn_cast in mn_details.mn_cast[:5]])
```

## Compatibility aliases

- `search_movies(...)` still works (alias to `mn_search_movies(...)`).
- `get_movie_details(...)` still works (alias to `mn_get_movie_details(...)`).

## Note

IMDb markup can change over time. If selectors change, this package may require updates.
