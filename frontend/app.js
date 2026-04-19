const API_BASE = (window.APP_CONFIG?.API_BASE_URL || "").trim() || window.location.origin;
const grid = document.getElementById("grid");
const latestRail = document.getElementById("latestRail");
const langBlocks = document.getElementById("langBlocks");
const hero = document.getElementById("hero");
const searchInput = document.getElementById("search");
const langFilter = document.getElementById("langFilter");
const yearFilter = document.getElementById("yearFilter");
const countEl = document.getElementById("movieCount");

let allMovies = [];

const normalize = (s) =>
  (s || "")
    .toLowerCase()
    .replace(/chapter|movie|part/gi, " ")
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();

const tokens = (s) => normalize(s).split(" ").filter(Boolean);

const thumbSrc = (m) => {
  if (!m.thumbnail) return "https://via.placeholder.com/500x750?text=No+Poster";
  if (m.thumbnail.startsWith("tg:")) return `${API_BASE}/api/media/${m.thumbnail.slice(3)}`;
  return m.thumbnail;
};

const safeTitle = (m) => {
  const t = (m?.title || "").trim();
  if (!t || /^tt\d{5,}$/i.test(t)) return "Untitled Movie";
  return t;
};

function similarity(title, q) {
  if (!q) return 1;
  const t = normalize(title);
  if (!t) return 0;
  if (t.includes(q)) return 3;
  const qTokens = tokens(q);
  const hit = qTokens.filter((x) => t.includes(x)).length;
  return hit / Math.max(qTokens.length, 1);
}

function card(movie, compact = false) {
  const genre = (movie.genres || []).slice(0, 2).join(" • ");
  return `
    <article class="poster ${compact ? "compact" : ""}" data-id="${movie.special_id}">
      <img src="${thumbSrc(movie)}" alt="${safeTitle(movie)}" loading="lazy" />
      <div class="overlay">
        <h3>${safeTitle(movie)}</h3>
        <p>${movie.year || ""}${movie.lang ? ` • ${movie.lang.toUpperCase()}` : ""}</p>
        ${genre ? `<small>${genre}</small>` : ""}
      </div>
    </article>
  `;
}

function attachCardClicks() {
  document.querySelectorAll(".poster").forEach((el) => {
    el.addEventListener("click", () => {
      const id = el.getAttribute("data-id");
      if (id) window.location.href = `/assets/movie.html?id=${encodeURIComponent(id)}`;
    });
  });
}

function renderHero(movie) {
  if (!movie) {
    hero.innerHTML = `<div class="hero-card"><h1>Direct Download Movie Hub</h1><p>Add movies via Telegram and stream-like browse instantly.</p></div>`;
    return;
  }
  hero.innerHTML = `
    <div class="hero-card">
      <img src="${thumbSrc(movie)}" alt="${movie.title || "Movie"}" />
      <div>
        <span class="chip">Featured</span>
        <h1>${safeTitle(movie)}</h1>
        <p>${movie.storyline || "Browse all latest uploads and language collections."}</p>
        <a class="cta" href="/assets/movie.html?id=${encodeURIComponent(movie.special_id)}">Watch Download Options</a>
      </div>
    </div>
  `;
}

function renderLanguageBlocks(movies) {
  const grouped = {};
  for (const m of movies) {
    const key = (m.lang || "Other").toUpperCase();
    grouped[key] = grouped[key] || [];
    grouped[key].push(m);
  }
  const langs = Object.keys(grouped).sort((a, b) => grouped[b].length - grouped[a].length).slice(0, 8);
  langBlocks.innerHTML = langs
    .map((lang) => {
      const cards = grouped[lang].slice(0, 12).map((m) => card(m, true)).join("");
      return `<div class="lang-section"><h3>${lang}</h3><div class="rail">${cards}</div></div>`;
    })
    .join("");
}

function applyFilters() {
  const q = normalize(searchInput.value);
  const lang = langFilter.value;
  const year = yearFilter.value;
  const filtered = allMovies
    .filter((m) => !lang || (m.lang || "").toLowerCase() === lang)
    .filter((m) => !year || String(m.year || "") === String(year))
    .map((m) => ({ m, score: similarity(m.title, q) }))
    .filter((x) => !q || x.score >= 0.6)
    .sort((a, b) => b.score - a.score)
    .map((x) => x.m);

  countEl.textContent = `${filtered.length} titles`;
  grid.innerHTML = filtered.map((m) => card(m)).join("");
  latestRail.innerHTML = allMovies.slice(0, 18).map((m) => card(m, true)).join("");
  renderLanguageBlocks(allMovies);
  attachCardClicks();
}

async function bootstrap() {
  const [moviesRes, langRes] = await Promise.all([
    fetch(`${API_BASE}/api/movies?page=1&page_size=200`),
    fetch(`${API_BASE}/api/meta/languages`),
  ]);
  if (!moviesRes.ok) throw new Error("Failed to load movies");

  const movieData = await moviesRes.json();
  allMovies = (movieData.items || []).filter((m) => m.title);
  renderHero(allMovies[0]);

  if (langRes.ok) {
    const langs = (await langRes.json()).items || [];
    langFilter.innerHTML = '<option value="">All Languages</option>';
    for (const l of langs) {
      const opt = document.createElement("option");
      opt.value = l;
      opt.textContent = l.toUpperCase();
      langFilter.appendChild(opt);
    }
  }

  applyFilters();
}

let t;
searchInput.addEventListener("input", () => {
  clearTimeout(t);
  t = setTimeout(applyFilters, 120);
});
langFilter.addEventListener("change", applyFilters);
yearFilter.addEventListener("change", applyFilters);

bootstrap().catch((err) => {
  grid.innerHTML = `<p class="error">${err.message}</p>`;
});
