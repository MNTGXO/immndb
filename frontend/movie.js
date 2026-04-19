const API_BASE = (window.APP_CONFIG?.API_BASE_URL || "").trim() || window.location.origin;
const wrap = document.getElementById("detailWrap");
const params = new URLSearchParams(window.location.search);
const id = params.get("id");

const thumbSrc = (m) => {
  if (!m.thumbnail) return "https://via.placeholder.com/500x750?text=No+Poster";
  if (m.thumbnail.startsWith("tg:")) return `${API_BASE}/api/media/${m.thumbnail.slice(3)}`;
  return m.thumbnail;
};

function row(label, value) {
  if (!value || (Array.isArray(value) && !value.length)) return "";
  return `<p><span>${label}</span>${Array.isArray(value) ? value.join(", ") : value}</p>`;
}

async function load() {
  if (!id) {
    wrap.innerHTML = '<p>Movie id missing. <a href="/">Go back</a></p>';
    return;
  }

  const res = await fetch(`${API_BASE}/api/movies/${encodeURIComponent(id)}`);
  if (!res.ok) {
    wrap.innerHTML = '<p>Movie not available. <a href="/">Go back</a></p>';
    return;
  }

  const m = await res.json();
  const links = (m.downloads || [])
    .map((l, i) => `<a class="dl-link" href="${l.url}" target="_blank" rel="noreferrer">${i + 1}. ${l.language} • ${l.quality}</a>`)
    .join("");

  wrap.innerHTML = `
    <a href="/" class="back-link">← Back to Home</a>
    <section class="detail-card">
      <img src="${thumbSrc(m)}" alt="${m.title || "Movie"}" />
      <div class="detail-main">
        <h1>${m.title || "Untitled movie"}</h1>
        <div class="meta-rows">
          ${row("Year", m.year)}
          ${row("Language", m.lang ? String(m.lang).toUpperCase() : "")}
          ${row("Rating", m.rating)}
          ${row("Votes", m.votes)}
          ${row("Runtime", m.runtime)}
          ${row("Genres", m.genres)}
        </div>
        ${m.storyline ? `<p class="story">${m.storyline}</p>` : ""}
        <h3>Download Links</h3>
        <div class="download-links">${links || "No links available"}</div>
      </div>
    </section>
  `;
}

load().catch((e) => {
  wrap.innerHTML = `<p>${e.message}</p>`;
});
