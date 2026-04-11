# immndb

`immndb` is a lightweight Python package that scrapes IMDb search and title pages.

## Features

- Search movies from IMDb with query strings (like `https://www.imdb.com/find/?q=kgf`)
- Extract movie titles and metadata from search results
- Support multi-page fetching via IMDb "More popular matches"
- Fetch complete movie details from title pages (`/title/tt.../`), including:
  - rating
  - year
  - storyline
  - cast
  - genres
  - release date
  - runtime
  - directors and writers

## Install

```bash
pip install -e .
```

## Usage

```python
from immndb import IMDbClient

client = IMDbClient()

results = client.search_movies("kgf", max_pages=3)
for movie in results:
    print(movie.imdb_id, movie.title, movie.year, movie.rating)

if results:
    details = client.get_movie_details(results[0].imdb_id)
    print(details.title)
    print(details.rating)
    print(details.storyline)
    print([c.name for c in details.cast[:5]])
```

## Notes

- IMDb markup can change over time. Selectors include fallback behavior but may require future updates.
- Use responsibly and respect IMDb's Terms of Use and robots policies.
