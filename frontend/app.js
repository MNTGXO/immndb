const API_BASE = window.APP_CONFIG?.API_BASE_URL || "http://localhost:8000";
const grid = document.getElementById("grid");
const searchInput = document.getElementById("search");
const langFilter = document.getElementById("langFilter");
const yearFilter = document.getElementById("yearFilter");
const countEl = document.getElementById("movieCount");
const refreshBtn = document.getElementById("refreshBtn");
const modal = document.getElementById("modal");
const modalBody = document.getElementById("modalBody");

async function fetchLanguages() {
  const res = await fetch(`${API_BASE}/api/meta/languages`);
  const data = await res.json();
  for (const lang of data.items || []) {
    const option = document.createElement("option");
    option.value = lang;
    option.textContent = lang.toUpperCase();
    langFilter.appendChild(option);
  }
}

function cardTemplate(movie, idx) {
  const genres = (movie.genres || []).slice(0, 3).map(g => `<span class="badge">${g}</span>`).join("");
  return `
    <article class="card" style="animation-delay:${idx * 40}ms">
      <img src="${movie.thumbnail_url || "https://via.placeholder.com/400x600?text=No+Poster"}" alt="${movie.title}"/>
      <div class="content">
        <h3>${movie.title}</h3>
        <small>${movie.year || "N/A"} • ${movie.lang || "unknown"} • ⭐ ${movie.rating || "-"}</small>
        <div class="badges">${genres}</div>
        <div class="actions">
          <a href="${movie.download_url}" target="_blank" rel="noopener noreferrer">Download</a>
          <button data-id="${movie.id}">Details</button>
        </div>
      </div>
    </article>
  `;
}

async function loadMovies() {
  const params = new URLSearchParams();
  if (searchInput.value.trim()) params.set("search", searchInput.value.trim());
  if (langFilter.value) params.set("lang", langFilter.value);
  if (yearFilter.value) params.set("year", yearFilter.value);

  const res = await fetch(`${API_BASE}/api/movies?${params}`);
  const data = await res.json();
  countEl.textContent = `${data.total} movies`;
  grid.innerHTML = data.items.map((m, i) => cardTemplate(m, i)).join("");

  document.querySelectorAll("button[data-id]").forEach(btn => {
    btn.addEventListener("click", () => showDetails(btn.dataset.id));
  });
}

async function showDetails(id) {
  const res = await fetch(`${API_BASE}/api/movies/${id}`);
  const m = await res.json();
  modalBody.innerHTML = `
    <h2>${m.title}</h2>
    <p>${m.storyline || "No storyline available."}</p>
    <p><b>Runtime:</b> ${m.runtime || "N/A"}</p>
    <p><b>Votes:</b> ${m.votes || "N/A"}</p>
    <p><b>Genres:</b> ${(m.genres || []).join(", ")}</p>
    <p><a href="${m.download_url}" target="_blank" rel="noopener noreferrer">Open direct link</a></p>
  `;
  modal.classList.remove("hidden");
}

document.getElementById("closeModal").addEventListener("click", () => modal.classList.add("hidden"));
modal.addEventListener("click", (e) => {
  if (e.target === modal) modal.classList.add("hidden");
});

let debounce;
searchInput.addEventListener("input", () => {
  clearTimeout(debounce);
  debounce = setTimeout(loadMovies, 250);
});
langFilter.addEventListener("change", loadMovies);
yearFilter.addEventListener("change", loadMovies);
refreshBtn.addEventListener("click", loadMovies);

fetchLanguages().then(loadMovies).catch(err => {
  grid.innerHTML = `<p>Could not load data: ${err.message}</p>`;
});
