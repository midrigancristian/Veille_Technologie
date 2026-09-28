(() => {
  const CAT_LABEL = {
    all: "Fil d'actualité",
    dev: "Développement",
    cyber: "Cybersécurité",
    sysadmin: "SysAdmin",
    ia: "Intelligence artificielle",
  };
  const CAT_SUB = {
    all: "Toutes les sources, agrégées et dédupliquées.",
    dev: "Langages, frameworks, outillage et open source.",
    cyber: "Vulnérabilités, menaces, reverse et défense.",
    sysadmin: "Linux, cloud, containers, observabilité.",
    ia: "Modèles, recherche, agents et outillage ML.",
  };
  const LS_FAV = "veille.favs";
  const LS_READ = "veille.read";

  const state = {
    mode: "api",
    category: "all",
    source: null,
    q: "",
    favorites: false,
    unread: false,
    offset: 0,
    limit: 28,
    hasMore: true,
    loading: false,
    items: [],
    pending: [],
    sources: [],
    snapshot: null,
  };

  const $ = (id) => document.getElementById(id);
  const feed = $("feed");
  const sentinel = $("sentinel");
  const empty = $("empty");
  const endMsg = $("endMsg");
  const newBanner = $("newBanner");
  const toastEl = $("toast");
  let toastTimer = null;
  let searchTimer = null;

  function toast(msg) {
    toastEl.textContent = msg;
    toastEl.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { toastEl.hidden = true; }, 2800);
  }

  function lsGet(key) {
    try {
      return new Set(JSON.parse(localStorage.getItem(key) || "[]"));
    } catch {
      return new Set();
    }
  }
  function lsSet(key, set) {
    localStorage.setItem(key, JSON.stringify([...set]));
  }
  function keyOf(item) {
    return item.guid || item.url || String(item.id);
  }

  function relTime(iso) {
    if (!iso) return "";
    const t = Date.parse(iso);
    if (Number.isNaN(t)) return "";
    const s = Math.max(0, (Date.now() - t) / 1000);
    if (s < 45) return "à l'instant";
    if (s < 3600) return `il y a ${Math.round(s / 60)} min`;
    if (s < 86400) return `il y a ${Math.round(s / 3600)} h`;
    if (s < 172800) return "hier";
    if (s < 86400 * 14) return `il y a ${Math.round(s / 86400)} j`;
    return new Date(t).toLocaleDateString("fr-FR", { day: "numeric", month: "short" });
  }

  function escapeHtml(str) {
    return String(str || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function extraBits(item) {
    const e = item.extra || {};
    const bits = [];
    if (e.points != null) bits.push(`${e.points} pts`);
    if (e.stars != null) bits.push(`★ ${Number(e.stars).toLocaleString("fr-FR")}`);
    if (e.language) bits.push(e.language);
    return bits;
  }

  function hydrateLocal(item) {
    const favs = lsGet(LS_FAV);
    const reads = lsGet(LS_READ);
    item.is_favorite = favs.has(keyOf(item));
    item.is_read = reads.has(keyOf(item));
    return item;
  }

  function itemNode(item, isNew) {
    const li = document.createElement("li");
    const a = document.createElement("article");
    a.className = `item${item.is_read ? " is-read" : ""}${isNew ? " is-new" : ""}`;
    a.dataset.id = item.id;
    const cat = item.category || "autre";
    const bits = extraBits(item)
      .map((b) => `<span>${escapeHtml(b)}</span>`)
      .join("");
    a.innerHTML = `
      <div class="bar ${escapeHtml(cat)}"></div>
      <div class="body">
        <div class="meta">
          <span class="src-name">${escapeHtml(item.source_name)}</span>
          <span>·</span>
          <time datetime="${escapeHtml(item.published_at || "")}">${relTime(item.published_at || item.fetched_at)}</time>
          <span class="pill ${escapeHtml(cat)}">${escapeHtml(CAT_LABEL[cat] || cat)}</span>
        </div>
        <h3><a class="title-link" href="${escapeHtml(item.url)}" target="_blank" rel="noopener noreferrer">${escapeHtml(item.title)}</a></h3>
        ${item.summary ? `<p class="summary">${escapeHtml(item.summary)}</p>` : ""}
        ${bits ? `<div class="extra">${bits}</div>` : ""}
      </div>
      <button class="star${item.is_favorite ? " is-on" : ""}" type="button" title="Favori" aria-label="Favori">
        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="1.7">
          <path d="M12 3.4l2.6 5.3 5.8.8-4.2 4.1 1 5.8L12 16.7 6.8 19.4l1-5.8L3.6 9.5l5.8-.8L12 3.4z"/>
        </svg>
      </button>
    `;
    a.querySelector(".star").addEventListener("click", (ev) => {
      ev.preventDefault();
      ev.stopPropagation();
      toggleFav(item, a.querySelector(".star"));
    });
    a.querySelector(".title-link").addEventListener("click", () => markRead(item, a));
    li.appendChild(a);
    return li;
  }

  function renderList(reset) {
    if (reset) feed.innerHTML = "";
    const frag = document.createDocumentFragment();
    if (reset) {
      for (const it of state.items) frag.appendChild(itemNode(it, false));
      feed.appendChild(frag);
    } else {
      const already = feed.querySelectorAll(".item").length;
      for (const it of state.items.slice(already)) frag.appendChild(itemNode(it, false));
      feed.appendChild(frag);
    }
    empty.hidden = state.items.length > 0 || state.loading;
    endMsg.hidden = state.hasMore || state.items.length === 0;
  }

  function showSkeletons() {
    feed.innerHTML = "";
    for (let i = 0; i < 7; i++) {
      const d = document.createElement("div");
      d.className = "skeleton";
      feed.appendChild(d);
    }
    empty.hidden = true;
    endMsg.hidden = true;
  }

  async function api(path, opts) {
    const res = await fetch(path, opts);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  function queryString() {
    const p = new URLSearchParams();
    if (state.category && state.category !== "all") p.set("category", state.category);
    if (state.source) p.set("source", state.source);
    if (state.q) p.set("q", state.q);
    if (state.favorites) p.set("favorites", "true");
    if (state.unread) p.set("unread", "true");
    p.set("offset", String(state.offset));
    p.set("limit", String(state.limit));
    return p.toString();
  }

  function matchesFilters(item) {
    if (state.favorites && !item.is_favorite) return false;
    if (state.unread && item.is_read) return false;
    if (state.category !== "all" && item.category !== state.category) return false;
    if (state.source && item.source_id !== state.source) return false;
    if (state.q) {
      const blob = `${item.title} ${item.summary}`.toLowerCase();
      if (!blob.includes(state.q.toLowerCase())) return false;
    }
    return true;
  }

  function filterSnapshot() {
    const all = (state.snapshot?.articles || []).map((a) => hydrateLocal({ ...a }));
    return all.filter(matchesFilters);
  }

  async function load({ reset = false } = {}) {
    if (state.loading) return;
    if (!reset && !state.hasMore) return;
    state.loading = true;
    if (reset) {
      state.offset = 0;
      state.hasMore = true;
      showSkeletons();
    }
    try {
      if (state.mode === "static") {
        const filtered = filterSnapshot();
        if (reset) state.items = filtered.slice(0, state.limit);
        else state.items = filtered.slice(0, state.offset + state.limit);
        state.hasMore = state.items.length < filtered.length;
        state.offset = state.items.length;
        renderList(reset);
      } else {
        const data = await api("/api/articles?" + queryString());
        if (reset) state.items = data.items;
        else state.items = state.items.concat(data.items);
        state.hasMore = data.has_more;
        state.offset = state.items.length;
        renderList(reset);
      }
    } catch (err) {
      console.error(err);
      toast("Impossible de charger le fil.");
      if (reset) {
        feed.innerHTML = "";
        empty.hidden = false;
      }
    } finally {
      state.loading = false;
    }
  }

  function staticStats() {
    const arts = (state.snapshot?.articles || []).map((a) => hydrateLocal({ ...a }));
    const by = {};
    const bySrc = {};
    let fav = 0;
    let unread = 0;
    for (const a of arts) {
      by[a.category] = (by[a.category] || 0) + 1;
      bySrc[a.source_id] = (bySrc[a.source_id] || 0) + 1;
      if (a.is_favorite) fav += 1;
      if (!a.is_read) unread += 1;
    }
    return {
      total: arts.length,
      favorites: fav,
      unread,
      by_category: by,
      by_source: bySrc,
      last_run: state.snapshot?.generated_at,
      fetching: false,
    };
  }

  async function refreshStats() {
    try {
      let stats;
      let sources;
      if (state.mode === "static") {
        stats = staticStats();
        sources = state.snapshot?.sources || [];
      } else {
        const [s, src] = await Promise.all([api("/api/stats"), api("/api/sources")]);
        stats = s;
        sources = src.sources || [];
      }
      $("favCount").textContent = stats.favorites ?? 0;
      const by = stats.by_category || {};
      document.querySelectorAll(".cat-n").forEach((el) => {
        const key = el.dataset.n;
        el.textContent = key === "all" ? (stats.total ?? "—") : (by[key] ?? 0);
      });
      state.sources = sources;
      renderSources();
      const last = stats.last_run;
      $("syncMeta").textContent = last
        ? (state.mode === "static" ? `Pages · ${relTime(last)}` : `Sync ${relTime(last)}`)
        : (stats.fetching ? "Synchronisation…" : "En attente de sync");
    } catch (e) {
      /* ignore */
    }
  }

  function renderSources() {
    const box = $("sources");
    box.innerHTML = "";
    for (const s of state.sources) {
      const b = document.createElement("button");
      b.type = "button";
      b.className = "src" + (state.source === s.id ? " is-active" : "");
      const cls = s.ok === true ? "ok" : s.ok === false ? "bad" : "wait";
      b.innerHTML = `<span class="src-dot ${cls}"></span><span>${escapeHtml(s.name)}</span><small>${s.last_count || ""}</small>`;
      b.addEventListener("click", () => {
        state.source = state.source === s.id ? null : s.id;
        updateHead();
        load({ reset: true });
        renderSources();
        closeSidebar();
      });
      box.appendChild(b);
    }
  }

  function updateHead() {
    const title = state.favorites
      ? "Favoris"
      : state.source
        ? (state.sources.find((s) => s.id === state.source)?.name || "Source")
        : CAT_LABEL[state.category];
    $("feedTitle").textContent = title;
    $("feedSub").textContent = state.favorites
      ? "Les articles que vous avez épinglés."
      : state.q
        ? `Recherche « ${state.q} »`
        : CAT_SUB[state.category] || "";
    document.querySelectorAll(".cat").forEach((c) => {
      c.classList.toggle("is-active", c.dataset.cat === state.category && !state.favorites);
    });
    $("favToggle").classList.toggle("is-on", state.favorites);
  }

  async function toggleFav(item, btn) {
    if (state.mode === "static") {
      const favs = lsGet(LS_FAV);
      const k = keyOf(item);
      if (favs.has(k)) favs.delete(k);
      else favs.add(k);
      lsSet(LS_FAV, favs);
      item.is_favorite = favs.has(k);
      btn.classList.toggle("is-on", item.is_favorite);
      refreshStats();
      return;
    }
    try {
      const updated = await api(`/api/articles/${item.id}/favorite`, { method: "POST" });
      item.is_favorite = updated.is_favorite;
      btn.classList.toggle("is-on", item.is_favorite);
      refreshStats();
    } catch {
      toast("Favori impossible.");
    }
  }

  async function markRead(item, node) {
    if (item.is_read) return;
    if (state.mode === "static") {
      const reads = lsGet(LS_READ);
      reads.add(keyOf(item));
      lsSet(LS_READ, reads);
      item.is_read = true;
      node.classList.add("is-read");
      refreshStats();
      return;
    }
    try {
      await api(`/api/articles/${item.id}/read`, { method: "POST" });
      item.is_read = true;
      node.classList.add("is-read");
      refreshStats();
    } catch { /* ignore */ }
  }

  async function doRefresh() {
    const btn = $("refresh");
    btn.classList.add("is-spin");
    try {
      if (state.mode === "static") {
        await loadSnapshot();
        toast("Fil rechargé depuis GitHub Pages.");
        await load({ reset: true });
        await refreshStats();
      } else {
        const r = await api("/api/refresh", { method: "POST" });
        if (r.reason === "already_running") toast("Sync déjà en cours…");
        else toast(`${r.inserted || 0} nouvel(le)s article(s)`);
        await load({ reset: true });
        await refreshStats();
      }
    } catch {
      toast("Échec de la synchronisation.");
    } finally {
      btn.classList.remove("is-spin");
    }
  }

  function connectSSE() {
    if (state.mode !== "api") return;
    const live = $("live");
    const es = new EventSource("/api/stream");
    es.onopen = () => live.classList.add("is-on");
    es.onerror = () => {
      live.classList.remove("is-on");
      live.classList.add("is-off");
      es.close();
      setTimeout(() => {
        live.classList.remove("is-off");
        connectSSE();
      }, 4000);
    };
    es.onmessage = (ev) => {
      live.classList.add("is-on");
      live.classList.remove("is-off");
      try {
        const data = JSON.parse(ev.data);
        if (data.type === "new") onNew(data);
        if (data.type === "status") {
          $("syncMeta").textContent = data.last_run
            ? `Sync ${relTime(data.last_run)}`
            : "Sync terminée";
          refreshStats();
        }
      } catch { /* ignore */ }
    };
  }

  function onNew(data) {
    const incoming = (data.articles || []).filter(matchesFilters);
    if (!incoming.length) {
      refreshStats();
      return;
    }
    const nearTop = window.scrollY < 80;
    if (nearTop && !state.q) {
      const known = new Set(state.items.map((i) => i.id));
      const fresh = incoming.filter((i) => !known.has(i.id));
      if (!fresh.length) return;
      state.items = fresh.concat(state.items);
      for (let i = fresh.length - 1; i >= 0; i--) {
        feed.insertBefore(itemNode(fresh[i], true), feed.firstChild);
      }
      empty.hidden = true;
      toast(`${fresh.length} nouvel(le)s article(s)`);
    } else {
      state.pending = data.articles || [];
      $("newBannerText").textContent =
        `${incoming.length} nouvel(le)s article(s) — afficher`;
      newBanner.hidden = false;
    }
    refreshStats();
  }

  newBanner.addEventListener("click", () => {
    newBanner.hidden = true;
    window.scrollTo({ top: 0, behavior: "smooth" });
    load({ reset: true });
  });

  document.querySelectorAll(".cat").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.category = btn.dataset.cat;
      state.favorites = false;
      updateHead();
      load({ reset: true });
      closeSidebar();
    });
  });

  $("favToggle").addEventListener("click", () => {
    state.favorites = !state.favorites;
    updateHead();
    load({ reset: true });
  });

  $("unreadOnly").addEventListener("change", (e) => {
    state.unread = e.target.checked;
    load({ reset: true });
  });

  $("search").addEventListener("input", (e) => {
    clearTimeout(searchTimer);
    searchTimer = setTimeout(() => {
      state.q = e.target.value.trim();
      updateHead();
      load({ reset: true });
    }, 280);
  });

  $("refresh").addEventListener("click", doRefresh);

  $("markRead").addEventListener("click", async () => {
    if (state.mode === "static") {
      const reads = lsGet(LS_READ);
      const arts = filterSnapshot();
      for (const a of arts) reads.add(keyOf(a));
      lsSet(LS_READ, reads);
      load({ reset: true });
      refreshStats();
      return;
    }
    await api("/api/read-all" + (state.category !== "all" ? `?category=${state.category}` : ""), {
      method: "POST",
    });
    load({ reset: true });
    refreshStats();
  });

  $("burger").addEventListener("click", () => {
    $("sidebar").classList.toggle("is-open");
    $("overlay").hidden = !$("sidebar").classList.contains("is-open");
  });
  $("overlay").addEventListener("click", closeSidebar);
  function closeSidebar() {
    $("sidebar").classList.remove("is-open");
    $("overlay").hidden = true;
  }

  document.addEventListener("keydown", (e) => {
    const tag = (e.target && e.target.tagName) || "";
    if (tag === "INPUT" || tag === "TEXTAREA") {
      if (e.key === "Escape") e.target.blur();
      return;
    }
    if (e.key === "/") {
      e.preventDefault();
      $("search").focus();
    } else if (e.key === "r" || e.key === "R") doRefresh();
    else if (e.key === "f" || e.key === "F") $("favToggle").click();
    else if (e.key === "1") document.querySelector('[data-cat="all"]').click();
    else if (e.key === "2") document.querySelector('[data-cat="dev"]').click();
    else if (e.key === "3") document.querySelector('[data-cat="cyber"]').click();
    else if (e.key === "4") document.querySelector('[data-cat="sysadmin"]').click();
    else if (e.key === "5") document.querySelector('[data-cat="ia"]').click();
  });

  const io = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) load({ reset: false });
  }, { rootMargin: "600px" });
  io.observe(sentinel);

  async function loadSnapshot() {
    const r = await fetch("articles.json?t=" + Date.now(), { cache: "no-store" });
    if (!r.ok) throw new Error("articles.json introuvable");
    state.snapshot = await r.json();
  }

  async function detectMode() {
    try {
      const ctrl = new AbortController();
      const t = setTimeout(() => ctrl.abort(), 900);
      const r = await fetch("/api/stats", { cache: "no-store", signal: ctrl.signal });
      clearTimeout(t);
      if (r.ok) return "api";
    } catch { /* static */ }
    return "static";
  }

  async function boot() {
    state.mode = await detectMode();
    const live = $("live");
    const label = live.querySelector(".live-label");
    if (state.mode === "static") {
      label.textContent = "pages";
      live.classList.add("is-on");
      live.title = "Mode GitHub Pages — mise à jour horaire via Actions";
      await loadSnapshot();
    } else {
      label.textContent = "live";
      connectSSE();
    }
    updateHead();
    await load({ reset: true });
    await refreshStats();
    if (state.mode === "api") setInterval(refreshStats, 60000);
  }

  boot().catch((err) => {
    console.error(err);
    empty.hidden = false;
    toast("Impossible d'initialiser Veille.");
  });
})();
