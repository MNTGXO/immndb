from dataclasses import dataclass, field
from typing import List, Optional


@dataclass(slots=True)
class MovieSearchResult:
    imdb_id: str
    title: str
    year: Optional[int] = None
    duration: Optional[str] = None
    certificate: Optional[str] = None
    poster_url: Optional[str] = None
    rating: Optional[float] = None
    votes: Optional[str] = None
    url: Optional[str] = None


@dataclass(slots=True)
class CastMember:
    name: str
    character: Optional[str] = None
    url: Optional[str] = None


@dataclass(slots=True)
class MovieDetails:
    imdb_id: str
    title: str
    original_title: Optional[str] = None
    year: Optional[int] = None
    rating: Optional[float] = None
    votes: Optional[int] = None
    storyline: Optional[str] = None
    genres: List[str] = field(default_factory=list)
    runtime: Optional[str] = None
    release_date: Optional[str] = None
    cast: List[CastMember] = field(default_factory=list)
    directors: List[str] = field(default_factory=list)
    writers: List[str] = field(default_factory=list)
    url: Optional[str] = None
