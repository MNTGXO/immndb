const API_BASE = (window.APP_CONFIG?.API_BASE_URL || "").trim() || window.location.origin;
const grid = document.getElementById("grid");
const searchInput = document.getElementById("search");
const langFilter = document.getElementById("langFilter");
const yearFilter = document.getElementById("yearFilter");
const countEl = document.getElementById("movieCount");
const refreshBtn = document.getElementById("refreshBtn");

const normalize = (s) => (s || "").toLowerCase().replace(/[^a-z0-9\s]/g, " ").replace(/\s+/g, " ").trim();

const thumbSrc = (m) => {
  if (!m.thumbnail) return "https://via.placeholder.com/400x600?text=No+Poster";
  if (m.thumbnail.startsWith("tg:")) return `${API_BASE}/api/media/${m.thumbnail.slice(3)}`;
  return m.thumbnail;
};

async function fetchLanguages() {
  const res = await fetch(`${API_BASE}/api/meta/languages`);
  const data = await res.json();
  langFilter.innerHTML = '<option value="">All Languages</option>';
  for (const lang of data.items || []) {
    const option = document.createElement("option");
    option.value = lang;
    option.textContent = lang.toUpperCase();
    langFilter.appendChild(option);
  }
}

function cardTemplate(movie, idx) {
  const title = movie.title || "Untitled movie";
  const genres = (movie.genres || []).slice(0, 3).map(g => `<span class="badge">${g}</span>`).join("");
  return `
    <article class="card" style="animation-delay:${idx * 45}ms" data-id="${movie.special_id}">
      <img src="${thumbSrc(movie)}" alt="${title}" loading="lazy"/>
      <div class="content">
        <h3>${title}</h3>
        <small>${movie.year || "N/A"} • ${movie.lang || "unknown"}</small>
        <div class="badges">${genres}</div>
        <div class="actions"><button data-id="${movie.special_id}">Open Details</button></div>
      </div>
    </article>
  `;
}

async function loadMovies() {
  const params = new URLSearchParams();
  const search = normalize(searchInput.value);
  if (search) params.set("search", search);
  if (langFilter.value) params.set("lang", langFilter.value);

  const res = await fetch(`${API_BASE}/api/movies?${params}`);
  const data = await res.json();
  let items = data.items || [];

  if (search) {
    items = items.filter((m) => normalize(m.title).includes(search));
  }
  if (yearFilter.value) {
    items = items.filter((m) => String(m.year || "") === String(yearFilter.value));
  }

  countEl.textContent = `${items.length} movies`;
  grid.innerHTML = items.map((m, i) => cardTemplate(m, i)).join("");

  document.querySelectorAll(".card, .actions button").forEach((el) => {
    el.addEventListener("click", () => {
      const id = el.getAttribute("data-id");
      if (id) window.location.href = `/assets/movie.html?id=${encodeURIComponent(id)}`;
    });
  });
}

let debounce;
searchInput.addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(loadMovies, 180); });
langFilter.addEventListener("change", loadMovies);
yearFilter.addEventListener("change", loadMovies);
refreshBtn.addEventListener("click", loadMovies);

fetchLanguages().then(loadMovies).catch((err) => { grid.innerHTML = `<p>Could not load data: ${err.message}</p>`; });
