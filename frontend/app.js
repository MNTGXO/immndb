const API_BASE = (window.APP_CONFIG?.API_BASE_URL || "").trim() || window.location.origin;
const grid = document.getElementById("grid");
const searchInput = document.getElementById("search");
const langFilter = document.getElementById("langFilter");
const yearFilter = document.getElementById("yearFilter");
const countEl = document.getElementById("movieCount");
const refreshBtn = document.getElementById("refreshBtn");
const modal = document.getElementById("modal");
const modalBody = document.getElementById("modalBody");

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
  const genres = (movie.genres || []).slice(0, 3).map(g => `<span class="badge">${g}</span>`).join("");
  const links = (movie.downloads || []).length;
  return `
    <article class="card" style="animation-delay:${idx * 45}ms">
      <img src="${thumbSrc(movie)}" alt="${movie.title}" loading="lazy"/>
      <div class="content">
        <h3>${movie.title}</h3>
        <small>${movie.year || "N/A"} • ${movie.lang || "unknown"} • ⭐ ${movie.rating || "-"}</small>
        <div class="badges">${genres}<span class="badge">${links} links</span></div>
        <div class="actions">
          <button data-id="${movie.special_id}">Download</button>
        </div>
      </div>
    </article>
  `;
}

async function loadMovies() {
  const params = new URLSearchParams();
  if (searchInput.value.trim()) params.set("search", searchInput.value.trim());
  if (langFilter.value) params.set("lang", langFilter.value);
  const res = await fetch(`${API_BASE}/api/movies?${params}`);
  const data = await res.json();

  const filtered = data.items.filter((m) => {
    if (!yearFilter.value) return true;
    return String(m.year || "") === String(yearFilter.value);
  });

  countEl.textContent = `${filtered.length} movies`;
  grid.innerHTML = filtered.map((m, i) => cardTemplate(m, i)).join("");
  document.querySelectorAll("button[data-id]").forEach(btn => btn.addEventListener("click", () => showDetails(btn.dataset.id)));
}

async function showDetails(specialId) {
  const res = await fetch(`${API_BASE}/api/movies/${specialId}`);
  const m = await res.json();
  const links = (m.downloads || []).map((l, i) => `<a class="dl-link" href="${l.url}" target="_blank">${i + 1}. ${l.language} • ${l.quality}</a>`).join("");
  modalBody.innerHTML = `
    <h2>${m.title}</h2>
    <p>${m.storyline || "No storyline available."}</p>
    <p><b>Runtime:</b> ${m.runtime || "N/A"} | <b>Votes:</b> ${m.votes || "N/A"}</p>
    <p><b>Genres:</b> ${(m.genres || []).join(", ")}</p>
    <p><b>Special ID:</b> ${m.special_id}</p>
    <div class="download-links">${links || "No links available"}</div>
  `;
  modal.classList.remove("hidden");
}

document.getElementById("closeModal").addEventListener("click", () => modal.classList.add("hidden"));
modal.addEventListener("click", (e) => { if (e.target === modal) modal.classList.add("hidden"); });

let debounce;
searchInput.addEventListener("input", () => { clearTimeout(debounce); debounce = setTimeout(loadMovies, 220); });
langFilter.addEventListener("change", loadMovies);
yearFilter.addEventListener("change", loadMovies);
refreshBtn.addEventListener("click", loadMovies);

fetchLanguages().then(loadMovies).catch((err) => { grid.innerHTML = `<p>Could not load data: ${err.message}</p>`; });
