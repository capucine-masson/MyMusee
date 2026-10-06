/* Page d'accueil : upload, analyse (2 étapes), œuvres proches, rerank, grounding, historique.
   Règle : tout texte venant du serveur ou d'API externes passe par textContent (jamais innerHTML). */
(() => {
  "use strict";
  const { boot, state, t, el, safeUrl, fmtMs, movementLabel, onLang } = window.Musee;
  const $ = (id) => document.getElementById(id);

  const ALLOWED = ["image/jpeg", "image/png", "image/webp"];
  const MAX_BYTES = 5 * 1024 * 1024;
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const ui = {
    form: $("upload-form"), file: $("file"), zone: $("dropzone"), dropEmpty: $("drop-empty"),
    dropPreview: $("drop-preview"), previewImg: $("preview-img"), previewName: $("preview-name"),
    previewSize: $("preview-size"), submit: $("submit"), submitLabel: $("submit-label"),
    stage: $("stage"), error: $("error"), errorMsg: $("error-msg"), errorDetail: $("error-detail"),
    banner: $("banner"), results: $("results"),
  };

  const app = { file: null, previewUrl: null, busy: false, current: null, timer: null };

  /* ------------------------------------------------------------ utilitaires */
  function show(node, on) { node.hidden = !on; }

  function showError(message, detail) {
    ui.errorMsg.textContent = message;
    ui.errorDetail.textContent = detail || "";
    show(ui.errorDetail, Boolean(detail));
    show(ui.error, true);
  }
  const clearError = () => show(ui.error, false);

  function setBusy(on) {
    app.busy = on;
    ui.form.classList.toggle("is-busy", on);
    ui.submit.disabled = on || !app.file;
    ui.file.disabled = on;
    ui.form.querySelectorAll('input[name="level"]').forEach((r) => (r.disabled = on));
    ui.submitLabel.textContent = t(on ? "btn.busy" : "btn.analyze");
    ui.submit.setAttribute("aria-busy", String(on));
    if (!on) setStage(null);
  }

  function setStage(key) {
    clearInterval(app.timer);
    if (!key) { show(ui.stage, false); return; }
    const started = performance.now();
    const tick = () => {
      ui.stage.textContent = `${t(key)} ${Math.floor((performance.now() - started) / 1000)} s`;
    };
    tick();
    show(ui.stage, true);
    app.timer = setInterval(tick, 500);
  }

  function fmtSize(bytes) {
    return bytes > 1024 * 1024 ? (bytes / 1048576).toFixed(1) + " Mo" : Math.round(bytes / 1024) + " Ko";
  }

  async function api(url, opts = {}, timeoutMs = 100000) {
    const ctrl = new AbortController();
    const to = setTimeout(() => ctrl.abort(), timeoutMs);
    try {
      const res = await fetch(url, {
        ...opts,
        headers: { ...(opts.headers || {}), "X-Lang": state.lang },
        signal: ctrl.signal,
      });
      let data = null;
      try { data = await res.json(); } catch (_) { /* corps non JSON */ }
      if (!res.ok) {
        const err = (data && data.error) || {};
        const generic = res.status === 413 ? t("err.size") : res.status === 415 ? t("err.type") : t("err.generic");
        throw { message: err.message || generic, detail: err.detail || null };
      }
      return data;
    } catch (e) {
      if (e && e.message !== undefined && e.name !== "AbortError" && !(e instanceof TypeError)) throw e;
      if (e && e.name === "AbortError") throw { message: t("err.timeout") };
      throw { message: t("err.network") };
    } finally {
      clearTimeout(to);
    }
  }

  /* ------------------------------------------------------------- sélection */
  function setFile(file) {
    clearError();
    if (!file) return;
    if (!ALLOWED.includes(file.type)) { showError(t("err.type")); return; }
    if (file.size > MAX_BYTES) { showError(t("err.size")); return; }
    if (app.previewUrl) URL.revokeObjectURL(app.previewUrl);
    app.file = file;
    app.previewUrl = URL.createObjectURL(file);
    ui.previewImg.src = app.previewUrl;
    ui.previewName.textContent = file.name;
    ui.previewSize.textContent = fmtSize(file.size);
    show(ui.dropEmpty, false);
    show(ui.dropPreview, true);
    ui.submit.disabled = app.busy;
  }

  ui.file.addEventListener("change", () => setFile(ui.file.files[0]));
  ["dragenter", "dragover"].forEach((ev) =>
    ui.zone.addEventListener(ev, (e) => { e.preventDefault(); if (!app.busy) ui.zone.classList.add("is-over"); }));
  ["dragleave", "drop"].forEach((ev) =>
    ui.zone.addEventListener(ev, (e) => { e.preventDefault(); ui.zone.classList.remove("is-over"); }));
  ui.zone.addEventListener("drop", (e) => {
    if (app.busy) return;
    const f = e.dataTransfer && e.dataTransfer.files[0];
    if (f) setFile(f);
  });
  ui.zone.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") { e.preventDefault(); if (!app.busy) ui.file.click(); }
  });
  // Empêche le navigateur d'ouvrir l'image si on la lâche à côté de la zone
  ["dragover", "drop"].forEach((ev) => window.addEventListener(ev, (e) => e.preventDefault()));

  /* ---------------------------------------------------------------- niveau */
  const levelRadios = ui.form.querySelectorAll('input[name="level"]');
  levelRadios.forEach((r) => {
    r.checked = r.value === boot.prefs.level;
    r.addEventListener("change", () => {
      fetch("/api/settings", {
        method: "PUT", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ level: r.value }),
      }).catch(() => {});
    });
  });
  const currentLevel = () => (ui.form.querySelector('input[name="level"]:checked') || {}).value || "enthusiast";

  /* --------------------------------------------------------------- envoi */
  ui.form.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (app.busy) return;
    if (!app.file) { showError(t("err.noimage")); return; }
    clearError();
    setBusy(true);
    app.current = null;
    ui.results.hidden = true;

    try {
      setStage("stage.vision");
      const fd = new FormData();
      fd.append("image", app.file);
      fd.append("lang", state.lang);
      fd.append("level", currentLevel());
      const first = await api("/api/analyze", { method: "POST", body: fd });
      app.current = { ...first, previewUrl: app.previewUrl, neighbors: [], before: [], grounding: null, errors: {} };
      renderAll();
      scrollToResults();
      refreshHistory();

      setStage("stage.similar");
      const fd2 = new FormData();
      fd2.append("image", app.file);
      fd2.append("history_id", String(first.history_id));
      fd2.append("lang", state.lang);
      const second = await api("/api/similar", { method: "POST", body: fd2 });
      app.current = { ...app.current, ...second };
      renderAll();
      refreshHistory();
    } catch (err) {
      showError(err.message || t("err.generic"), err.detail);
    } finally {
      setBusy(false);
    }
  });

  function scrollToResults() {
    ui.results.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "start" });
  }

  /* ------------------------------------------------------------- rendu */
  function renderAll() {
    const d = app.current;
    if (!d) return;
    show(ui.results, true);
    renderAnalysis(d);
    renderSimilar(d);
    renderGrounding(d);
    renderTimings(d);
  }

  function badge(conf) {
    return el("span", { class: `badge badge-${conf}`, text: t("conf." + conf) });
  }

  function renderAnalysis(d) {
    const a = d.analysis;
    show($("analysis"), true);
    const img = $("analysis-img");
    const hasImg = Boolean(d.previewUrl);
    if (hasImg) img.src = d.previewUrl;
    show(img, hasImg);
    show($("analysis-noimg"), !hasImg);

    const cartel = $("cartel");
    cartel.replaceChildren();
    const row = (label, ...vals) => {
      cartel.append(el("dt", { text: label }));
      cartel.append(el("dd", null, ...vals));
    };
    const txt = (s) => document.createTextNode(s || "—");
    const artistText = a.artist_guess || t("artist.unknown");
    row(t("field.movement"), txt(a.movement), a.movement ? badge(a.movement_confidence) : null);
    row(t("field.period"), txt(a.period));
    row(t("field.technique"), txt(a.technique));
    row(t("field.artist"), txt(artistText), a.artist_guess ? badge(a.artist_confidence) : null);

    const chips = $("elements");
    chips.replaceChildren(...(a.elements || []).map((x) => el("li", { class: "chip note", text: x })));
    $("explanation").textContent = a.explanation || "";
  }

  function rankNote(n, idx, hasRerank) {
    if (!hasRerank) return "";
    const pos = idx + 1;
    if (n.rank_before > 5) return t("card.rank.new", { n: n.rank_before });
    const delta = n.rank_before - pos;
    if (delta > 0) return t("card.rank.up", { n: delta });
    if (delta < 0) return t("card.rank.down", { n: -delta });
    return t("card.rank.same");
  }

  function renderSimilar(d) {
    const has = d.neighbors && d.neighbors.length > 0;
    show($("similar"), has);
    if (!has) return;
    const hasRerank = !d.errors.rerank;
    const gallery = $("gallery");
    gallery.replaceChildren();

    d.neighbors.forEach((n, i) => {
      const li = el("li", { class: "card reveal", attrs: { "data-id": n.id, "data-i": String(i) } });
      const frame = el("div", { class: "frame" });
      const mat = el("div", { class: "mat" });
      const url = safeUrl(n.image_url);
      if (url) {
        const img = el("img", {
          attrs: { src: url, alt: `${n.title}${n.artist ? " — " + n.artist : ""}`, loading: "lazy", referrerpolicy: "no-referrer" },
        });
        img.addEventListener("error", () => img.replaceWith(el("p", { class: "noimg note", text: t("card.noimg") })));
        mat.append(img);
      }
      frame.append(mat);

      const cartel = el("div", { class: "cartel note" });
      cartel.append(el("span", { class: "idx", text: `[${i + 1}]` }));
      cartel.append(el("strong", { class: "card-title", text: n.title }));
      cartel.append(el("span", { text: n.artist || t("artist.unknown") }));
      cartel.append(el("span", { text: [n.year, movementLabel(n.movement)].filter(Boolean).join(" · ") }));

      const scores = el("p", { class: "scores note" });
      scores.append(el("span", { text: `${t("card.cosine")} ${n.cosine.toFixed(3)}` }));
      if (hasRerank && n.rerank_score != null) scores.append(el("span", { text: `${t("card.rerank")} ${n.rerank_score.toFixed(3)}` }));

      const note = rankNote(n, i, hasRerank);
      const foot = el("p", { class: "src note" });
      const href = safeUrl(n.source_url);
      if (href) foot.append(el("a", { text: t("card.source") + " ↗", attrs: { href, target: "_blank", rel: "noopener noreferrer" } }));
      foot.append(el("span", { class: "lic", text: n.license || "" }));

      li.append(frame, cartel, scores);
      if (note) li.append(el("p", { class: "rank note", text: note }));
      li.append(foot);
      gallery.append(li);
    });

    renderBeforeAfter(d, hasRerank);
  }

  function renderBeforeAfter(d, hasRerank) {
    const before = $("ba-before"), after = $("ba-after"), note = $("ba-note");
    before.replaceChildren(); after.replaceChildren();
    const beforeIds = d.before.map((b) => b.id);
    let changes = 0;
    d.before.forEach((b, i) => {
      const moved = hasRerank && d.neighbors[i] && d.neighbors[i].id !== b.id;
      before.append(el("li", { class: moved ? "moved" : "", text: `${b.title} (${b.cosine.toFixed(3)})` }));
    });
    d.neighbors.forEach((n, i) => {
      const moved = hasRerank && beforeIds[i] !== n.id;
      if (moved) changes += 1;
      after.append(el("li", { class: moved ? "moved" : "", text: `${n.title}${hasRerank && n.rerank_score != null ? ` (${n.rerank_score.toFixed(3)})` : ""}` }));
    });
    note.textContent = !hasRerank ? t("ba.skipped") : changes ? t("ba.changed", { n: changes }) : t("ba.same");
  }

  function highlightCard(id) {
    const card = document.querySelector(`.card[data-id="${CSS.escape(id)}"]`);
    if (!card) return;
    card.scrollIntoView({ behavior: reduceMotion ? "auto" : "smooth", block: "center" });
    card.classList.add("flash");
    setTimeout(() => card.classList.remove("flash"), 1600);
  }

  function renderGrounding(d) {
    const g = d.grounding;
    show($("grounding"), Boolean(g));
    if (!g) return;
    const box = $("ground-text");
    box.replaceChildren();
    const indexOf = (id) => d.neighbors.findIndex((n) => n.id === id);
    for (const seg of g.segments) {
      if (!seg.doc_ids.length) { box.append(document.createTextNode(seg.text)); continue; }
      const span = el("span", { class: "cited", text: seg.text });
      const refs = seg.doc_ids.map(indexOf).filter((i) => i >= 0);
      if (refs.length) {
        const sup = el("sup", { class: "cite-ref note" });
        refs.forEach((i, k) => {
          const b = el("button", { class: "cite-btn", text: String(i + 1), attrs: { type: "button", "aria-label": `${d.neighbors[i].title}` } });
          b.addEventListener("click", () => highlightCard(d.neighbors[i].id));
          if (k) sup.append(document.createTextNode(","));
          sup.append(b);
        });
        span.append(sup);
      }
      box.append(span);
    }
    const list = $("ground-sources");
    list.replaceChildren(el("li", { text: t("ground.cites", { n: g.n_citations }) }));
  }

  function renderTimings(d) {
    const list = $("timing-list");
    list.replaceChildren();
    let total = 0;
    (d.timings || []).forEach((m) => {
      total += m.ms;
      list.append(el("li", null,
        el("span", { class: "step", text: t("step." + m.step) }),
        el("span", { class: "model", text: m.model }),
        el("span", { class: "ms", text: fmtMs(m.ms) })));
    });
    list.append(el("li", { class: "total" }, el("span", { class: "step", text: "Total" }), el("span", { class: "model" }), el("span", { class: "ms", text: fmtMs(total) })));
    show($("timings"), (d.timings || []).length > 0);
  }

  /* ------------------------------------------------------------ historique */
  const hist = { list: $("history-list"), empty: $("history-empty"), clear: $("history-clear") };

  function renderHistory(items) {
    app.historyItems = items;
    hist.list.replaceChildren();
    show(hist.empty, items.length === 0);
    show(hist.clear, items.length > 0);
    items.forEach((it) => {
      const when = new Date(it.created_at).toLocaleString(state.lang === "fr" ? "fr-FR" : "en-GB", { dateStyle: "short", timeStyle: "short" });
      const btn = el("button", { class: "hist-btn", attrs: { type: "button" } },
        el("span", { class: "hist-sum", text: it.summary || "—" }),
        el("span", { class: "hist-date note", text: when }));
      btn.addEventListener("click", () => openHistory(it.id));
      hist.list.append(el("li", null, btn));
    });
  }

  async function refreshHistory() {
    try { renderHistory(await api("/api/history", {}, 15000)); } catch (_) { /* non bloquant */ }
  }

  async function openHistory(id) {
    if (app.busy) return;
    clearError();
    try {
      const item = await api(`/api/history/${id}`, {}, 15000);
      app.current = { history_id: item.id, previewUrl: null, neighbors: [], before: [], grounding: null, errors: {}, ...item.result };
      renderAll();
      scrollToResults();
    } catch (err) {
      showError(err.message || t("err.generic"));
    }
  }

  hist.clear.addEventListener("click", async () => {
    try {
      await api("/api/history", { method: "DELETE" }, 15000);
      renderHistory([]);
    } catch (err) { showError(err.message); }
  });

  /* --------------------------------------------------------- bannière état */
  function renderBanner() {
    const s = boot.status;
    const key = !s.has_key ? "banner.nokey" : s.corpus_embedded === 0 ? "banner.nocorpus" : null;
    if (key) ui.banner.textContent = t(key);
    show(ui.banner, Boolean(key));
  }

  onLang(() => {
    renderBanner();
    setBusy(app.busy);
    renderHistory(app.historyItems || boot.history);
    renderAll();
  });

  /* ---------------------------------------------------------------- départ */
  renderBanner();
  renderHistory(boot.history);
  ui.submit.disabled = true;
})();
