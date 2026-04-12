const API_BASE = (window.APP_CONFIG?.API_BASE_URL || "").trim() || window.location.origin;
const wrap = document.getElementById("detailWrap");
const params = new URLSearchParams(window.location.search);
const id = params.get("id");

const thumbSrc = (m) => {
  if (!m.thumbnail) return "https://via.placeholder.com/400x600?text=No+Poster";
  if (m.thumbnail.startsWith("tg:")) return `${API_BASE}/api/media/${m.thumbnail.slice(3)}`;
  return m.thumbnail;
};

function row(label, value) {
  if (!value || (Array.isArray(value) && value.length === 0)) return "";
  return `<p><b>${label}:</b> ${Array.isArray(value) ? value.join(", ") : value}</p>`;
}

async function load() {
  if (!id) {
    wrap.innerHTML = '<p>Movie id missing. <a href="/">Go back</a></p>';
    return;
  }
  const res = await fetch(`${API_BASE}/api/movies/${encodeURIComponent(id)}`);
  if (!res.ok) {
    wrap.innerHTML = '<p>Movie not found. <a href="/">Go back</a></p>';
    return;
  }
  const m = await res.json();
  const links = (m.downloads || []).map((l, i) => `<a class="dl-link" href="${l.url}" target="_blank">${i + 1}. ${l.language} • ${l.quality}</a>`).join("");

  wrap.innerHTML = `
    <a href="/" class="dl-link" style="width:max-content">← Back</a>
    <section class="detail-card">
      <img src="${thumbSrc(m)}" alt="${m.title || "Movie"}"/>
      <div>
        <h1>${m.title || "Untitled movie"}</h1>
        ${row("Year", m.year)}
        ${row("Language", m.lang)}
        ${row("Rating", m.rating)}
        ${row("Votes", m.votes)}
        ${row("Genres", m.genres)}
        ${row("Runtime", m.runtime)}
        ${m.storyline ? `<p>${m.storyline}</p>` : ""}
        <h3>Download Links</h3>
        <div class="download-links">${links || "No links available"}</div>
      </div>
    </section>
  `;
}

load().catch((e) => {
  wrap.innerHTML = `<p>Error: ${e.message}</p>`;
});
