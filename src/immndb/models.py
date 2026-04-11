from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(slots=True)
class MovieSearchResult:
    mn_imdb_id: str
    mn_title: str
    mn_year: Optional[int] = None
    mn_duration: Optional[str] = None
    mn_certificate: Optional[str] = None
    mn_poster_url: Optional[str] = None
    mn_rating: Optional[float] = None
    mn_votes: Optional[str] = None
    mn_url: Optional[str] = None


@dataclass(slots=True)
class CastMember:
    mn_name: str
    mn_character: Optional[str] = None
    mn_url: Optional[str] = None


@dataclass(slots=True)
class MovieDetails:
    mn_imdb_id: str
    mn_title: str
    mn_original_title: Optional[str] = None
    mn_year: Optional[int] = None
    mn_rating: Optional[float] = None
    mn_votes: Optional[int] = None
    mn_storyline: Optional[str] = None
    mn_plot_preview: Optional[str] = None
    mn_genres: List[str] = field(default_factory=list)
    mn_runtime: Optional[str] = None
    mn_release_date: Optional[str] = None
    mn_certificate: Optional[str] = None
    mn_cast: List[CastMember] = field(default_factory=list)
    mn_stars: List[str] = field(default_factory=list)
    mn_directors: List[str] = field(default_factory=list)
    mn_writers: List[str] = field(default_factory=list)
    mn_budget: Optional[str] = None
    mn_gross_us_canada: Optional[str] = None
    mn_gross_worldwide: Optional[str] = None
    mn_country_of_origin: List[str] = field(default_factory=list)
    mn_languages: List[str] = field(default_factory=list)
    mn_production_companies: List[str] = field(default_factory=list)
    mn_aka: Optional[str] = None
    mn_streaming_links: List[str] = field(default_factory=list)
    mn_url: Optional[str] = None
    mn_raw_sections: Dict[str, str] = field(default_factory=dict)
